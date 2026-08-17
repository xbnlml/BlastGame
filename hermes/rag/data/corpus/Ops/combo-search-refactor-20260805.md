# 组合搜索算法拆分到 find_best_combo.py（2026-08-05 架构重构）

## 背景：为什么拆分

`pool.py` 原本混了两层职责：**数据访问层**（读 stage-data JSON、dedup、filter_verified）+ **算法层**（find_best_monotonic 找最优五档组合）。算法被写死在 pool.py 里，19 个模块被迫从"数据池"import 算法，单一职责被破坏，算法无法单独测试/复用。

用户质疑："为什么独立出来的东西是套壳而实际的写死在某个大模块里？"——`find_best_combo.py` 原本只是 CLI 壳，实际调用 `pool.find_best_monotonic`。

## 拆分后结构

```
tools/find_best_combo.py    ← 算法本体 + CLI 入口（find_best_monotonic/_gap_score/
                               target_pen_seg/_bucket/_find_monotonic_3tier）
tools/data/pool.py          ← 纯数据层（get_all_records/dedup/filter_verified/
                               _source_penalty/_config_key/_norm_of）+ 延迟转发
```

**关键决策（无循环依赖）**：
- `_source_penalty`/`_config_key`/`_norm_of` **留在 pool.py**——它们被数据层（dedup_records 用 `_source_penalty`）和算法层共用，不能搬走
- `find_best_combo.py` 顶部 `from tools.data import pool` 拿这些辅助函数
- pool.py **末尾用延迟 import 转发**（函数内 import，不是文件顶部）：
  ```python
  def find_best_monotonic(records, targets, top_n=1, difficulty='hard'):
      from tools.find_best_combo import find_best_monotonic as _fbm
      return _fbm(records, targets, top_n=top_n, difficulty=difficulty)
  ```
  延迟 import 避免加载时循环依赖（find_best_combo 顶部 import pool，若 pool 顶部 import find_best_combo → 循环）。加载时无循环，运行时才 import，此时 pool 已加载完。

**12 个调用方零改动**：agent_analyze/judge_level/design_probes/reimport_batch/state_snapshot/preflight/post_batch_review/compare_imported/auto_loop 等直接调 `pool.find_best_monotonic` 的行为不变（转发）。

## ⚠️ 发现的老性能缺陷：O(k^5) 暴力枚举

`find_best_monotonic` 的 5-tier 枚举是 O(k^5)（5 层嵌套 for + `_bucket` 每档取 60 条候选 → 60^5 ≈ 7.8 亿组合）。随数据量指数爆炸：

| verified 条数 | 耗时 |
|--------------|------|
| 10 | 0.00s |
| 20 | 0.28s |
| 30 | 7.18s |
| 40 | 33.53s |
| 81 (L200) | >40s 超时 |

**⚠️ 上述"性能缺陷"结论是误导，已被推翻（2026-08-05 会话末）**：root cause 不是 O(k^5) 算法慢，而是 **`find_best_combo.py` main 误用 `pool.get_preferred_records`（含 phase1/phase2，81 条）**，正确应 `filter_verified`（9 条 verified）。改用 filter_verified 后 L200 **0.4s 即时跑完**，多关 0.5s。**推断依据**：81 条里 phase1/phase2 数据多触发枚举爆炸；verified 只有 9 条。拆分前后算法代码相同所以"拆分前 30 条也慢"是正常的（未 filter_verified 都会慢），不是算法本身缺陷。

**真正教训**：① `find_best_combo.py` 必须 filter_verified（坑 2 铁则：phase1/2 不能用于入库决策）——已修复 main 改用 `get_all_records + filter_verified + dedup_records`。② 遇到"某 CLI 对特定关慢/超时"，先查它用的数据源是否 filter_verified，别急着归因算法复杂度优化。③ 算法复杂度本身（O(k^5) 枚举）在 verified 数据量小的场景下不是瓶颈，不需要优化 bucket/剪枝。

## 验证

拆分回归 5/5 通过（编译/pool 数据层函数保留/延迟转发可用/小数据选组合一致/调用方 import 正常）。行为一致：拆分后 20 条选 [69.4,58.5,40.5,26.4,17.1]，与拆分前相同。