# 关卡数据库白/红/绿判定 + 池子全量数据（2026-08-07）

> 触发：用户问"哪些关能让数据库变好 / 减少红色 / 增加绿色"、"某关胜率范围"。
> 教训：不要凭 find_best_combo 的"能贴目标组合"去回答 DB 状态——那是两回事，用户要的是**DB 当前实际是白还是红**。

## 一、关卡数据库 entry 结构（关键，别再用错）

LevelDatabase/Run/test.json 的 entry 是 **每档一条**（单档结构），不是"五档组合 entry"：
- 每条 entry 有：`dealConfig`（该档 sd/sc/ratios/of）、`winRate`（该档胜率，0~1）、`sourceTierLabels`（标 T1~T5）、`matchedAssetSlots`、`identitySource`/`identityStatus`
- **没有 `tierConfigs` 数组**（165/182 等也是单档）

⚠️ **compare_level_db.py 因此对 101-150 全部误报"无活动entry"**——它找的是 `tierConfigs` 匹配的 entry，而 DB 里都是单档 `dealConfig`。**该工具对逐个资产五档匹配不可靠**，别用它判 DB 白/红/绿。

## 二、正确判定方法（每档匹配 asset 配置 → 对比目标）

```python
# 每关：取 asset 5 档配置，每档在 DB entries 里找 dealConfig 与 asset 该档一致的 entry，取其 winRate
# 再对比目标（normal 85/85/65/50/50, hard 70/55/40/30/20, superhard 50/40/30/20/10）
# 活动 entry = dealConfig 的 sd/sc/ratios/of 与 asset 该档完全一致的那条
```

判定（相对目标）：
- **白** = 该档无匹配 entry（无数据）
- **🔴红** = 该档 winRate 偏差 >15pp
- **🟡黄** = 偏差 10~15pp
- **🟢绿** = 偏差 ≤10pp

DB 前端红黄字标准：`abs(实测-目标) ≤0.10` 绿 / `≤0.15` 黄 / `>0.15` 红（与 rules.json target_deviation 一致）。

## 三、胜率范围 = 合并所有数据源（用户强调）

问"某关胜率范围"时，**必须合并全部数据源**，不能只查 phase1 或只查池子：
- telemetry 批次：`phase1_raw.csv`（phase1）、`phase2_candidates.csv`（phase2）、`summary.csv`（summary）
- 池子：`get_all_records(lv)`（已含 phase0/phase1/phase2/summary/bot，通过 load_bot+load_assist+load_ref）

**池子本该是全量的**——如果池子缺某关数据（如 phase1 缺失），先查是不是**池子过期**，不是猜 bug：
- 池子文件 mtime（stage-data/{lv}/*.json）**早于** telemetry 批次 mtime → 池子最后 dump 在批次生成之前，最新数据没导入
- 修复：重跑 `dump_level_pools.py` 把最新批次导入
- 牌面校验（`_opt_snapshot_valid`）若全通过，则不是牌面问题，优先看 mtime

## 四、判断"能否改善 DB"（用户原话：减少红色/白色/增加绿色）

能改善 = 该关数据的**胜率范围覆盖到目标段**（如 normal 需覆盖到 85/65/50）。
- 覆盖到目标段 → 能用可靠数据（summary/phase0/bot）更新 DB 对应档位
- 覆盖不到目标段（天花板低于目标，如 normal 最高才 64%）→ 数据改善不了，需要**改关卡**而非写 DB

示例结论（2026-08-07 批次 110/119/120/136/138/144）：
- L110 全数据 0~82%（phase0/1/2/summary）→ T3(65)/T4/5(50) 段有，可改善部分档位
- L136 48~100% → 85/65/50 全段有，可填满全 5 档
- L119/120/138/144 天花板 45~67% → 够不到 85，改善不了，需改关卡