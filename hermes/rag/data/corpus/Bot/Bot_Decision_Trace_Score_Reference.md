# Bot Decision Trace 评分字段对照手册

面向 **decision-trace JSON** 的人工比对。

**实现入口**：
- Beam 主流程：`Assets/GameModule/Editor/Bot/BlastBotService.Decision.cs`（**未改**剪枝/beam/聚合）
- 新总分：`Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Formula.cs`
- 特征一次构建：`Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Features.cs`
- Breakdown：`Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Breakdown.cs`
- **运行时系数覆盖**：`BlastBotScoringTuneKnobs` ← `telemetry/bot/scoring-tune.json`（批跑启动加载；见 `Doc/AI/2026-07-10-bot-scoring-auto-tune.md`）

---

## 1. 节点总分（ScoringOptVg）

策略：`BlastBotStrategy.ScoringOptVg` / 导出名 `scoring_opt_vg`。  
实现：`Assets/GameModule/Editor/Bot/Scoring/Vg/*`。

breakdown 字段名与语义如下：

| 项 | 含义 |
|----|------|
| EffectiveCoverage | 同色多槽：gate 时用 `a_min`，否则 `sumAmmo`；写入 thirst/idle 用的 fireable 覆盖 |
| slotSparePenalty | 并入 `slotPressureAndIdlePenalty`；empty 3/2/1/0 → 0/80/420/900 |
| sameColorWaste | `(sum−coverage)×k` 并入 idle |
| secretExploreBonus | `f(unmetGap, knownIdle)` 连续式，非仅「近渴未盖」布尔 |
| Hold | `bestPlace < waitBaseline`（coverage/empty/secret/attackLiveness）；Trace 同时导出拒绝原因、`bestPlace`、`waitBaseline`、覆盖/浪费、三合计数与 Wait 后进展 |
### 1.1 Wait Trace

每个决策步新增 `waitDecision`。它用于区分“没有进入等待”“进入等待但被安全门拒绝”“等待后确实产生进展”，并记录同色延迟落子预算；这些字段本身不叠加额外评分。`remainingGoalsBefore` 在决策步落盘时统一从同一份状态写入，非等待分支也不会再保留默认 `0`。

- 门控：`hasAttackOpportunity`、`hasHighVisibleImmediateDemandCandidate`、`totalBottomNeed`、`resolvableBottomNeed`、`uncoveredBottomNeed`、`coverageFraction`、`waitMinCoverage`、`waitMaxUncoveredNeed`。
- 比较：`waitBaseline`、`bestPlace`、`urgentDirectPlacementScore`、`placementUtility`、`waitUtility`、`waitAdvantage`、`estimatedReleaseMs`、`waitBudgetMs`、`waitBatchMs`、`waitMargin`、`attackLiveness`、`secretScore`、`emptySlots`、`slotAmmoTotal`。
- 结构：`hasImmediateMergeCandidate`、`mergeReadyTypeCount`、`mergeAlmostTypeCount`。Ready Link/当前落子即可完成的三合才属于 Wait 硬门；`CanTriggerMergeSoon` 仅表示可延迟的高价值路径，应进入 placement utility 比较。
- 数量：`bottomNeedByColor`、`slotAmmoByColor`、`fireableAmmoByColor`、`reservedAmmoByColor`、`effectiveCoverageByColor`、`wasteByColor`、`waitColor`、`releaseColor`、`expectedAttackShots`、`expectedAmmoDrain`、`expectedReleasePotential`。
- 实际结果：`selected`、`decision`、`advanceMs`、`waitWindowCount`、`cumulativeWaitMs`、`estimatedReleaseMs`、`waitBudgetMs`、`waitBatchMs`、`hasAttackOpportunityAfter`、`emptySlotsAfter`、`remainingGoalsAfter`、`slotsAfter`、`objectiveHealthBefore`、`objectiveHealthAfter`、`objectiveProgressObserved`、`attackProgressObserved`、`waitedColorAmmoProgressObserved`、`structuralProgressObserved`、`releaseObserved`、`forcePlacementAfterWait`、`sameColorWaitNoReleaseWindows`、`progressObserved`。同色等待的 `releaseObserved/releaseColor` 只表示等待颜色实际释放；Objective Health 或其他颜色 ammo 变化单独不等价于等待颜色槽位消耗。
- 候选分类：`hasHardActionCandidate`、`urgentDirectPlacement`、`valuableReveal`、`redundantSameColor` 及对应的候选列字段。候选事实并行收集，同一列可以同时出现在 reveal 和 redundant 列表；`hasHighVisibleImmediateDemandCandidate` 仅为诊断，不再单独否决冗余等待。
- shortlist：`subsetSelectionPath=vg_uncovered_reveal_force` 表示 ScoringOptVg 在紧槽位且底行缺色时，先从原始 `allLegal` 收集并保留用于揭示缺色的候选列，再与过滤后的 beam 合并；`one-plus-two` 的容量冲突按颜色计算，实际三合仍按 `(color, triangle)` 计算。

`decision` 常见值包括 `no_attack_opportunity`、`coverage_gate_rejected`、`no_resolvable_bottom_need`、`hard_action_candidate`、`direct_urgent_beats_wait`、`redundant_same_color_wait`、`wait_utility_beats_placement`、`placement_beats_wait_utility`、`placement_beats_wait_baseline`、`wait_baseline_beats_placement`、`legacy_wait_selected`。这些字段可用于区分候选分类失败、效用比较失败和实际等待无结构释放，不应同时叠加多个表达同一意图的惩罚项。

| shortlist deep | 权重 0.75/0.45/0.20；无 `×0.08`；两跳 UrgentBuried |

Trace 当前等待字段版本为 `waitDecision:v6`，并包含 `candidateFacts:v1`；候选行额外记录 `candidateTriangle`、`candidateShape`、`hardNow`、`mergeSoon`、`valuableReveal`、`redundantSameColor`、`urgentDirect`。若 `waitedColorAmmoProgressObserved=false` 且连续窗口没有释放，应由强制落子保护终止等待；即使 ammo 正在减少，也必须受目标颜色释放 deadline 与全局 Wait budget 约束。

Replay 诊断中，下一次落子记录的 `waitStartFrame`、`waitEndFrame`、`waitDurationMs` 与 `waitWindowCount` 只描述 Bot Wait 元数据，不作为 gameplay action；带有该元数据的间隔不会被播放器的大空档 fast-forward 压缩。

运行时优化的验收边界：
- `VgDecisionFrameContext` 的字段按 Hold/shortlist 语义隔离，并绑定单个未变更的 `state/candidates/slots` 快照；Clone 或 settle 后不得复用旧帧。
- Root Hold 与 shortlist 可复用同一帧的派生结果，但 `holdImmediateNeed`、`shortlistWeightedNeed`、fireable/reserved ammo、slot color/type 和 surface type 不能混用。
- Trace 开启时 ScoringOptVg 根节点的 total 与 breakdown 必须来自一次评分；Trace 不能改变总分、候选顺序、Wait/落子结论或随机顺序。
- 批量 worker 的 options、template 和配置快照只读；线程局部策略状态与进度轮询优化不得改变每个 seed 的动作摘要、终局原因或胜率。
- 批量摘要不再输出 `runtime.*` 性能对拍字段（2026-07-28 拆除）。

详见 `Doc/AI/2026-07-14-scoring-opt-vg.md`。

---

## 2. reachCost 启发式（禁止嵌套掉落仿真）

- 普通列：自底向上**前缀 health**（每列一遍，不对每格再扫下方）
- Snake：组剩余伤害，每组计一次（ThreadLocal 去重）
- Pool/2x2：读块 health
- Gate：路径断开（代价 999）
- 前排 Lock 且无底行 Key：该列 +8
- 短期/长期分界：**4 health**
- fireable：`BuildSlotSupplyContext(..., bottomY)` 复用底行；Trace 下 score+breakdown 只 Build 一次 Features

---

## 3. 空转（stagnation）

- `stagnationSteps < 3` → 罚分 0
- `≥3` → `(s-2)²×140`
- 变好：boardHealth 下降、remaining 下降、emptySlots 上升（合并腾槽）
- Objective 单独降血 **不算** 变好

---

## 4. 相关文档

- 计划与维度说明：`.cursor/plans/vg_scoring_refactor_e00f3eed.plan.md`
- 权重回拉（L20/L29 死锁）：`Doc/AI/2026-07-10-vg-weight-retune-deadlock.md`
- 架构：`Doc/Bot/Bot_Architecture.md`
