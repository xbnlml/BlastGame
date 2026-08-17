# auto_loop planner JSON 解析失败 → extract_json 多行 JSON 修复（2026-08-08）

> 场景：auto_loop 启动 85/119/120 全自动调优，ROUND 1 立即失败 `probe_design_failed_r1` ×3 关。
> 关联：`scripts/auto_loop.py`（编排器）、`tools/planner.py`（探针设计，`--output json`）。

## 症状
```
[Phase 1/5] agent_analyze → combo + design_probes
  planner: could not parse JSON output
  3 level(s) missing probes — running fallback design_probes...
  (fallback 写了探针，planner 重跑仍解析失败)
❌ Errors: 3 levels — probe_design_failed_r1
```

## 根因
- `planner.py --output json` 用 `json.dumps(results, indent=2)` 输出**多行格式化 JSON**，且 `analyze_level()` 内部的 debug print（"① 当前最优… ③ 探针目标…"）混入 stdout——JSON 前面有普通文本。
- `auto_loop.extract_json()` 原实现只支持**单行 JSON**（`line.startswith('{')` + 整行 parse）→ 多行 JSON 每个 `{` 行都不闭合 → 全部失败 → 返回 None → probe_design_failed_r1。

## 修复（extract_json 增加 brace-span 提取）
策略顺序：① 末行单行 JSON → ② **first '{' .. last '}' 区间整体 parse（支持多行 JSON + 前后噪声）** → ③ 整个 stdout → ④ 首行单行 JSON。核心新增：
```python
start = stdout.find('{')
end = stdout.rfind('}')
if start >= 0 and end > start:
    try:
        return json.loads(stdout[start:end + 1])
    except json.JSONDecodeError:
        pass
```

## 排查要点（下次遇到 auto_loop 立即失败）
1. 先看 `auto-log/<时间戳>.log` 的 `planner: could not parse JSON output` + `stdout preview`——**preview 前 200 字符能直接看出 JSON 前面混了什么**。
2. `planner.py --levels X --output json` 手动跑一次，检查 stdout 结构（多行 vs 单行、是否有 debug 噪声）。
3. 修 extract_json 后 ad-hoc 验证：真实 planner 输出能解析 + 单行 JSON 回归 + 纯噪声返回 None。
4. 另一个坑：验证脚本用 `exec()` 提取函数时命名空间要注入 `json`，否则 NameError 误报。

## 关联教训
- auto_loop 全自动启动前，planner JSON 链路是第一个阻塞点；日志里 `probe_design_failed_r1` = 探针设计阶段失败，先查 planner 输出解析，不是探针本身问题。
- 改关卡检测方法：`find <Generated_enum/test> -name "*.asset" -newermt "2026-08-08 00:00" ! -newermt "2026-08-09 00:00"` 列出当天改过的 asset（用户手动改关卡 = asset mtime 变化，15:29-15:38 连续批量改 7 关是典型特征）。
