# Curator Memory

## 分工铁则

讨论或调优 BlastGame 关卡时，具体分析由对应确定性入口执行，主 Agent 负责调用、核验和展示：

| 任务 | 权威入口 |
|---|---|
| 探针设计 | Planner / `design_probes.py` |
| 组合选择 | Planner / `agent_analyze.py` |
| 判定与轮次 | Judge / `judge_level.py` |
| 安全校验 | Warden |
| 经验统计 | Curator |

Curator 不修改规则、asset、Excel、board 或 LevelDatabase。规则只认 `project-state/rules.json`，入库和改关卡必须由用户确认。

## 自动统计有效性

### 2026-08-25 — 历史统计作废说明
- 2026-07-31 至 2026-08-22 的自动“错误: 1”记录由旧解析器按标题行计数产生，不代表每轮真实有一个错误。
- 同期“通过入库”标签也已被当前“合格待确认入库”语义取代。
- 不可核验的自动统计已从 memory 移除；原始 `auto-log/` 仍是历史证据。
- 新统计只接受完整的结构化 FINAL SUMMARY：Passed（待确认入库）/Failed（改关卡）/Errors 三个明确数字。
- 多轮阶段顺序按每轮独立状态机验证；“接近”是合法判定态并继续消耗轮次。
