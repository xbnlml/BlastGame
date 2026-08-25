# 文档索引

30 秒定位任何文档。

## 核心文档（先看这些）

| 文档 | 内容 | 何时看 |
|---|---|---|
| `design-decisions.md` | **8 个核心设计决策**（ADR 六段式：背景/方案对比/为什么/代价/教训）| 想理解系统"为什么这么设计" |
| `demo-guide.md` | 离线 Replay、Live Smoke 与回归入口 | 想先实际运行再读实现 |
| `../README.md` | 项目全景 + 流程 + 验证入口 | 刚接触项目 |
| `../tools/README.md` | 工具索引（按"想做什么"查）| 做任何操作前 |
| `../rag/README.md` | 当前 RAG 构建、严格评估口径与已知边界 | 使用或评估 RAG |

## 设计文档（design/）

| 文档 | 主题 |
|---|---|
| `knowledge-layer-architecture.md` | 知识六层分层架构（USER/MEMORY/SKILL/references/RAG/session）|
| `target-winrate-design-20260814.md` | 目标胜率历史设计（T3 anchor 内容已退役）|
| `target-winrate-period-tiering-20260814.md` | 目标胜率分段历史方案（T3 anchor 内容已退役）|
| `experience-curve-period-layering-20260814.md` | 体验曲线历史方案（T3 anchor 内容已退役）|
| `experience-scale-review-20260814.md` | 体验尺度历史评审（执行规则以 rules.json 为准）|
| `period-tier-reachability-review-20260814.md` | 分段档位可达性评审 |
| `unity_batchmode_csv_research.md` | Unity 批跑 CSV 导出研究 |
| `blastgame-skill-slim-plan-20260814.md` | Skill 瘦身方案 |
| `game-economy-inflation-scheme.xlsx` / `game-economy-inflation-impl-note.md` | 游戏数值膨胀系统设计（方案 + 实现说明）|
| `play-on-offer-design.md` | 复活礼包设计 |
| `r1a-wave-plan-review-20260807.md` / `phase1_intent_first_redesign.md` | 早期流水线设计评审 |

## 调研文档（research/）

| 文档 | 主题 |
|---|---|
| `BlastGame_RAG_选型方案.md` / `rag-proposal-v1/v2.md` | RAG 系统选型与方案演进 |