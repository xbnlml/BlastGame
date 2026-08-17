# Blast Bot 当前架构


## 分层与依赖

```text
Core ← Sim ← Runtime/UI ← Editor
```

- Core：数据/常量/共享接口（纯 C#）。
- Sim：纯仿真规则与状态推进（无 UI 副作用）。
- Runtime/UI：局内编排与可视化。
- Editor（Bot）：任务驱动、批跑调度、导出，不复制玩法规则。

## Bot 服务职责拆分

| 类 / 文件 | 职责 | 协作者 |
|---|---|---|
| `BlastBotService` | 单局/批跑入口与执行编排 | `BlastBotScorerVg` / `BlastBotClonePool` |
| `BlastBotService.Decision` | 候选生成与动作选择 | Scorer / Sim |
| `BlastBotScorerVg` + `BlastBotScoring.*` | 评分计算模块化拆分 | `BlastBotScoringContext` |
| `BlastBotClonePool` | 快照克隆与对象复用 | Service 仿真分支 |
| `BlastBotBatchRunner` / `BlastBotRangeRunner` / `BlastBotCampaignRunner` | 多场景执行调度与导出 | Service / Export |

## 协作边界

- 统一内核为 `RunSingleInternal`；不同入口只在“参数装配与批次调度”层差异。
- Bot 不经过 GameMain Controller 逻辑壳，直接使用共享 Sim 规则推进。
- Beam 分支状态绝不写回真局；性能优化不改变 seed 结果、动作序列和终局判定。
- 共享规则真源：`BlastGameLogic.TickCombat` 与槽位状态推进口径；规则变更必须同步 Runtime/Bot 校验。

## Parity 红线

- 不改变随机调用顺序、合法列集合与排序、终局判定顺序。
- Runtime/Bot 共享战斗入口与槽位状态推进口径；Stage 与 Slot 均空时直接判胜，规则变更必须同步校验。


## Bot 文件结构（恢复）

Bot 代码全部在 `Assets/GameModule/Editor/Bot/` 下，按职责拆分为多个 partial 文件：

| 文件 | 职责 |
|------|------|
| `BlastBotService.cs` | 入口与基础调度（`RunBatch`/`RunSingle`/初始化模板）；`RunSingleInternal` 通过 `try/finally` 归还 state/candidates/slots 到 ThreadLocal pool |
| `BlastBotService.Decision.cs` | `ScoringOptVg` beam search 主流程；节点评分统一调用 `BlastBotScorerVg` |
| `Scoring/Vg/BlastBotScorerVg.cs` | 唯一评分入口；经 `BlastBotScoringContext` 组合子模块 |
| `Scoring/BlastBotScoringContext.cs` | 单次 beam 节点评分输入；`SearchNodeState` |
| `Scoring/BlastBotScoring.Penalties.cs` | 惩罚项 |
| `Scoring/BlastBotScoring.Demand.cs` | 棋盘色需求 + `FillWeightedImmediateRowsNeed` |
| `Scoring/BlastBotScoring.Snapshot.cs` | 快照综合分 |
| `Scoring/BlastBotScoring.Pressure.cs` | 压力/稳定 |
| `Scoring/BlastBotScoring.Special.cs` | 特殊块/Pool 压力 |
| `Scoring/BlastBotScoring.Filters.cs` | L33 预筛选分、`ScoreCandidateColor` 等 |
| `Scoring/BlastBotScoring.Link.cs` | Link 可达性、`SlotSideMultiDimScore`、`ScoreLinkBlockerClearingBonus` |
| `Scoring/BlastBotScoring.SlotSupply.cs` | 槽供给账本：`fireable` / `reserved` 弹药、`slotCountByType`（solo+link 成员） |
| `BlastBotDecisionTrace.cs` | Workbench 决策 Trace DTO / 记录器 |
| `BlastBotDecisionTrace.Subset.cs` | subset 剪枝诊断收集（`legalColumnAnalysis`） |
| `BlastBotDecisionTraceRunner.cs` | Workbench「导出决策Trace」入口 |
| `Scoring/BlastBotScoring.Breakdown.cs` | `EvaluateGreedyBreakdown` 分项（trace 根模拟） |
| `Pool/BlastBotClonePool.cs` | ThreadLocal 对象池、`CloneState`、`Rent*`/`Return*`、`RunWithPoolCompression` |
| `BlastBotService.Simulation.cs` | 拟人延迟窗口、`RunBotCombatTick` 战斗推进 |
| `BlastBotService.SimulationTail.cs` | `SettleCombatFully`、beam 预筛选编排、队列填充、模板与内部类型 |
| `BlastBotService.RunModels.cs` | Bot 结果 DTO（`BlastBotRunResult` / `BlastBotBatchResult`） |
| `BlastBotService.RunOptions.cs` | Bot 输入配置（`BlastBotRunOptions` / `BlastBotStrategy`） |
| `BlastBotService.Campaign.cs` | 战役相关 helper 与 score tracker |
| `BlastBotService.Editor.cs` | Editor 绑定与共享配置快照注入 |
| `BlastBotRunPolicy.cs` | 运行策略编排（seed 生成、worker 调度） |
| `BlastBotBatchRunner.cs` | 批量运行编排与导出 |
| `BlastBotCampaignRunner.cs` | 战役编排器，`ResolvePackName` 从 `BlastBotCampaignOptions.levelFolderName` 读取分组名 |
| `BlastBotReplayExport.cs` | 回放记录与导出 |
| `BlastBotRangeRunner.cs` | 关卡范围运行与导出，`LoadLevelFromScriptableObject` 按 `(gameLevel, folderName)` 动态构造路径 |
| `BlastBotHumanConfig.cs` | 拟人参数配置 |
| `BlastMultiTierOptimizer.cs` | 多档位参数优化器（Phase0–3）；构造时把当前 `LevelProfileConfig` `.asset` 快照到关卡 telemetry 的 `level-assets/`；细节见 `Doc/Bot/bot_optimization.md` |
| `BlastMultiTierPhase1AdaptiveSampler.cs` | Phase1：R1a ratio preset 广覆盖、R1b 曲线二分补洞（每段≤2）、R2 未满足档邻域等量加密（`densifyPerSeed` 默认 4，可接 searchSeed 有界微扰）；已删除旧 Round3 / 75% 均分逻辑 |
| `BlastMultiTierTargetAdjuster.cs` | Multi-Tier 目标胜率调整器：基于 Phase1 胜率分布生成 `ConfiguredTargetWinRate` / `EffectiveTargetWinRate` 与 clamp 标记 |
| `BlastWorkbenchWindow.MultiTierOpt.cs` | Workbench 多档位优化面板与 Jenkins 对齐入口 |
| `BlastMultiTierExcelConfigReader.cs` | 解析 `Assets/LvEditorConfig/lv_win_config_{分组}.xlsx`：优先读取**第二行英文字段名**（`level`/`difficulty`/`tier1~tier5`/`failDist`）建立列映射，再解析数据行；无字段行时回退旧版固定列布局；`MultiTierExcelLevelConfig.DifficultyLevel` 写入 `MultiTierConfig.difficultyLevel` 并导出到 `summary.csv`/`detail.csv`；summary/detail 含 `BoardFingerprint` 与单条 `DealFingerprint`，供中控双指纹匹配；供 Multi-Tier 区间批量运行及 Workbench 切换关卡时按关卡覆盖目标参数 |
| `BlastLevelGroup.cs` + `ResourcePathData.GeneratedEnumRoot` | 分组枚举与 `funnel_b`/`test` 字面量仅在 `BlastLevelGroupUtil`；`GetKnownFolderNames` / `NormalizeSelection` 供 Workbench 分组下拉；SO 根路径仅在 `ResourcePathData`；默认目录名统一 `BlastLevelGroupUtil.DefaultFolderName` |
| `BlastLevelRangeParser.cs` | 通用关卡表达式解析（如 `1-10,12,15,20-30` → 去重升序关卡列表）；`BuildFolderTag` 为关卡目录标签唯一真源 |
| `BlastBotExportPathConfig.cs` | 批跑/Campaign/Multi-Tier 导出路径统一经 `BuildLevelFolderTag` 组装（Bot 批跑 `BuildBotBatchRangeTag`、Campaign `BuildCampaignLevelRangePrefix`）；Bot/MultiTier 共用 `WriteBatchResultMarker`（`bot-batch-last-result.properties` / `multitier-batch-last-result.properties`） |
| `BlastBotJenkinsBatchEntry.cs` | Bot 区间批跑 Jenkins CLI 入口，支持 `-BlastBotBatchLevels` / `-BlastBotBatchRunCount` / `-BlastBotBatchTiers` / `-BlastBotBatchRecordReplay`；有关卡失败仍 Exit(0) |
| `BlastMultiTierJenkinsBatchEntry.cs` | Multi-Tier Jenkins 批量 CLI 入口，支持 `-BlastMultiTierLevels` / `-BlastMultiTierLevelFolder` |

Multi-Tier Bot 编辑器代码保持使用接口类型（如 `IReadOnlyList`、`ISet`）传递集合，避免调用具体集合实现的专有成员。

Sim 层仿真引擎（纯 C#，被 Bot 直接调用）：

| 文件 | 职责 |
|------|------|
| `Sim/BlastEngine.cs` | 方块管理、drop/refill |
| `Sim/BlastQueueBuilder.cs` | 队列构建 |
| `Sim/BlastAttackSystem.cs` | 攻击系统常量和类型定义 |
| `Sim/BlastAttackSystem.State.cs` | 攻击系统状态（冷却、row sweep、special focus、普通待攻击队列） |
| `Sim/BlastAttackSystem.Update.cs` | `UpdateAttacks` 主循环（shooter 遍历、目标选择、战场推进） |
| `Sim/BlastAttackSystem.AttackOnce.cs` | `SlotAttackOnce`（单次射击的分支处理） |
| `Sim/BlastAttackSystem.Targeting.cs` | 目标选择算法 |
| `Sim/BlastAttackSystem.SpecialBlocks.cs` | 特殊方块（2x2/gate/snake）解析 |
| `Sim/BlastKeyLockResolver.cs` | Key-lock 配对 + 延迟解锁（纯数据，Bot/Runtime 共享） |
| `Sim/BlastGameLogic.cs` | 完整战斗 tick `TickCombat`（纯数据，Bot/Runtime 共享入口） |

## 执行流程

1. 读取关卡配置并构造 `BlastGameState`。
2. 构造初始 slots、candidates、queue 和 difficulty context。
3. 根据策略生成可见候选动作。
4. 对候选执行快照克隆、落子、`TickCombat` 和 settle。
5. 用评分器选择动作，写回真局状态。
6. 直到胜利、失败或无可执行动作，输出结果和可选 replay。

Bot 真局与 Beam/lookahead 必须区分：

- 真局推进使用正常时间窗口和状态转移。
- Beam 只用于评估，不得把评估分支状态写回真局。
- Beam 的 `SettleCombatFully` 可使用 `dt=0`，这不是主循环时间推进。
- **终局探针** `ProbeFullSettleSnapshot` / `SettleCombatFullyForTerminalProbe` 使用正 `replayFixedDeltaMs` 与独立 tick 上限（默认 4096），用于 Closing/落地锁/冷却收口；达到预算仍 `Running` 不得判永久死局。Beam 评分 settle 保持零时间 oracle，二者不得混用。

## 策略与评分

### ScoringOptVg

唯一策略。使用可见信息边界生成候选，并结合有效弹药覆盖、Hold、shortlist 与深层评分选择动作；不得读取玩家不可见信息。

### 评分输入

评分器可以使用：

- 剩余可清除单位和目标进度；
- slot 可攻击性、合成机会和阻塞；
- Gate、Snake、Key-Lock、Block2x2 等特殊结构；
- 候选动作带来的 settle、队列和攻击结果。

评分器不得修改快照之外的共享状态，也不得嵌套执行完整掉落仿真来计算 `reachCost`。

## Runtime / Bot 状态一致性

- `BlastGameLogic.TickCombat` 是共享战斗 tick 入口。
- `AdvanceSlotStates` 先于 `UpdateAttacks`，避免 FlyingIn 尚未收口时被误判为可攻击。
- `FlyingIn` 和 `Merging` 不可攻击；只有满足 `CanSlotAttack` 的 `Occupied` 槽可攻击。
- `TryMergeSlots` 只接受状态已收口的有效槽位。
- Bot 的非攻击过渡折叠由 `BlastBotNonAttackTransitionFoldPolicy` 显式控制。
- 终局暂缓：`ShouldDeferFailureForTransientState`（槽位过渡 + 棋盘 Closing + 落地锁）；与 `HasAttackOpportunityRuntime` 正交。
- Runtime、Bot、Replay 的规则变化必须同步检查 `Gameplay_Rules_Logic.md` 和 `Bot_Runtime_Slot_State_Parity.md`。

## 随机、回放与输出

- 每局 seed 必须显式生成并记录，保证同一输入可复现。
- Bot 输出应包含关卡、策略、seed、结果、结束原因和必要的时间/步数信息。
- 失败 `endReason` 保留细分路径（如 `terminal_deadlock_post_window_failed`），**不再折叠成 `deadlock`**；局末追加 `|class=…|board=…|pool=…|queue=…|slotAmmo=…|legal=…|attack=…`。
  - `deadlock_real`：槽满且无攻击机会，候补已空。
  - `suspect_stock`：候补仍有余量却不能打不能落（stock/stage 可能对不上）。
  - `suspect_near_miss`：槽内弹药数量盖得住残留单位却打不出。
  - `suspect_transient`：落地/Closing 未收口却已判负。
  - `deadlock_other`：其余失败。
- replay 元数据按需生成；批跑默认不为每个分支生成完整 replay。
- Debug trace 只用于定位分歧，不改变评分或状态。

## 性能边界

- 优先复用 clone、候选集合、队列前缀和临时容器，减少 Beam GC。
- 可缓存不随候选变化的派生数据，但不得跨局共享可变玩法状态。
- 性能优化不得改变胜率、动作顺序、时间轴或 replay 结果。
- 不使用 `Thread.Sleep` 模拟人类延迟；延迟只进入仿真时间轴参数。

## 验收清单

- 同一关卡和 seed 可复现相同结果。
- Bot 真局与 Runtime 的 `TickCombat` 顺序一致。
- Beam 只读取和修改自己的快照。
- Bot 不读取不可见信息。
- 评分和性能优化没有改变玩法规则。
- 需要定位实现时，优先使用本文入口和 `Doc/MainGame/module-index/`，不要查归档或已删除计划。
