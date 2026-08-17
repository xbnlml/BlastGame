# Gameplay Rules Logic（玩法规则）

本文对应 `Playbooks/gameplay-rules-logic.md`，聚焦“攻击系统、特殊块、下落补块、队列构建与规则约束”。

## 1. 核心职责模块

- `BlastLevelLoader`：把关卡数据转换为 `BlastGameState / Slots / Candidates`。
- `BlastAttackSystem`：目标选择、攻击推进、命中/销毁事件。
- `BlastEngine`：下落、补块、特殊结构处理。
- `BlastStageController`：候选入槽、候选推进、槽位合并逻辑。

## 2. 关键规则口径

### 2.1 `Block2x2` 攻击候选约束

- 仅当该 `2x2` 组内仍存活格子的最大 `y` 等于当前 `curBottomRow` 时，允许进入可攻击候选。
- 未到第一行则不可被攻击。
- `Block2x2` 仍作为一个特殊目标组参与选择，不拆成 4 个独立目标。
- `Block2x2` 组内颜色不再在加载/normalize 阶段强制同色；保留每格原始颜色。
- `Block2x2` 组锚点识别与 `TowerValue/health` 脱钩：无 `block2x2Id` 时按 `Block2x2` 结构识别候选锚点并归组，`block2x2Id` 为空视为数据异常，不在 UI 层做兼容兜底。
- 命中预算口径：
  - 四格同色：沿用 `TowerValue`（该颜色独占预算）。
  - 四格非同色：按每格 `10` 次累计到颜色预算（总计 `40`）。
  - shooter 仅可命中“自己颜色仍有预算”的 `Block2x2`；预算耗尽后该颜色不再可打。
- 组总剩余击数 = 各颜色预算和；该值用于特殊目标同类型 tie-break 的“剩余击数”比较。
- 预算归零时仍按整组一次性移除并触发下落，维持原有“大格子”消除语义。

### 2.2 攻击目标队列与特殊块插队

- 普通目标按颜色进入跨 `UpdateAttacks()` 调用保存的普通待攻击队列；某颜色队列未耗尽前，该颜色的新下落普通块不进入本轮普通攻击候选。
- 队列耗尽按“当前 shooter 颜色是否仍有未消费且仍位于入队坐标的普通目标”判断；其他颜色的旧队列不阻塞当前颜色进入下一轮普通候选。
- 普通目标 row sweep 状态按攻击 slot 独立保存：每个 slot 只推进自己的 cursor；cursor 表示普通队列中的稳定起扫位置，不是过滤后临时候选列表下标；当该颜色普通队列重建或队列底行变化时，该 slot cursor 从 0 重新开始。
- 普通目标在 shooter 开火瞬间懒选择：每次 ready shooter 都重新从普通队列过滤 alive、未消费、引用仍在原坐标且可命中的候选，不维护 `slot -> target` 预定表。
- 普通队列候选还需满足“当前仍是该列前沿块”（`TryGetColumnFrontLiving`：占格挡看穿，Closing 则本列无目标）。若其下方存在 Closing/未清阻挡，该候选无效。
- 攻击候选须落在当前全局 `bottomRow`：Closing 抬住底行时，其它列也只能打该底行活块，不能打到上一行（第二格）。
- 同色多个 slot 同时 ready 时按 ready 顺序串行选择；同一次 `UpdateAttacks()` 内已被普通攻击命中的坐标会写入临时 reservation，后续 ready slot 会跳过该坐标；若目标被击杀，再写入 consumed key 持续避免重复命中已消费目标。
- 普通队列快照保存颜色、入队坐标与已消费颜色坐标 key；命中前通过 `ReferenceEquals(state.GetBlock(x, y), target)` 校验，避免对象池复用或下落后误命中新块。
- 特殊块目标每次 shooter 选择前实时扫描当前底行；新下落特殊块允许插队。特殊目标先按类型优先级选择：`Objective > Snake > Gate > Block2x2`，类型优先级高于 special focus；同类型内再继续按 special focus、剩余击数、坐标 tie-break 选择。
- `Gate` 攻击采用“头部门控”：即使 body/尾部颜色可匹配，只要当前 `GetGateAttackTarget`（头部）对 shooter 不可命中（例如颜色不匹配），整组本次都不可攻击。
- `Gate` 进入特殊候选的前提是“头部在当前全局底行且列前沿暴露”。
- `Gate` **刚性整组下落**：支撑清空后按完整占地逐行 Settle（与 Block2x2 同为组移动）；`gateGroupId` 仅关卡初始化 `BuildGateGroups` 建立，Settle 后不重建，避免独立 Gate 落地相邻后误合并。组内任一 Closing 占位时整组既不可攻击也不可下落。
- 失败判定中的“是否仍可攻击”（`HasAttackOpportunity / HasAttackOpportunityRuntime`）与真实开火路径（`UpdateAttacks`）必须保持同口径：
  - `Block2x2` 仅在“该组有效底行 == 当前 bottomRow”时才算可攻击；
  - `Gate` / 普通 / Snake / Objective 均须在当前 `bottomRow` 且列前沿可打。
  - 目的：避免“判定层认为还能打，但实战层打不出去”导致失败弹板无法触发。
- **“不可攻击”与“瞬态延迟判负”是两个谓词**：
  - `HasAttackOpportunityRuntime`：当前底行是否真有可开火目标（Closing 占位挡列前沿时为 false，口径正确）。
  - `BlastGameLogic.ShouldDeferFailureForTransientState(state, slots)`：主槽过渡态（`ShouldDeferMainSlotFailure`）、棋盘 Closing 占位（`BlastBoardClosing.HasPendingClosingOccupancy`）、**或**落地锁未清（`BlastBoardDropLanding.HasPendingDropLanding`）时暂缓永久失败。
  - Runtime `HasEliminableBlockForSlots` / Bot `TakeDecisionSnapshot` / `GetSessionOutcomeLikeH5` 共用后者；不得把 Closing / 落地空窗误判为死局。
- `TryMergeSlots` 的等级门禁默认仍走 `BlastGameController.Instance.CurrentGameLevel`；Bot/Headless 并行仿真则在主线程预缓存 `BlastMergeSimContext`（`notMergeLv` / `mergeFlyDurationMs` / `levelNumber`），经 `TickCombat` 与落子链路透传，worker 不再读 ScriptableObject 或 `Instance`。
- 玩家态额外特例：当主槽仅 1 空位且前排仅剩连体候选并且当前不可放置时，`EvaluateRunState` 不自动结束关卡（等待玩家主动返回）；Bot 仿真仍按常规死局判负。
- `HasEliminableBlockForSlots` 将“即将进入 Closing”的耗尽槽位（`BlastGameLogic.HasSlotsDepletedPendingClose`）视为仍可收口：单体需 `Occupied && ammo<=0`，连体需整组都 `Occupied && ammo<=0`；若仅部分耗尽则不延迟判负。

### 2.2.1 攻击系统实例与开局重置

- Runtime `BlastGameController` 在槽位数不变时复用同一 `BlastAttackSystem` 实例；Bot 仿真每局 `new BlastAttackSystem()`。
- `LoadLevel` 成功后调用 `ResetAllCombatTargetingState()`（在 `ResetCooldowns()` 之后），清空：
  - 按颜色的普通攻击队列与 `bottomRowsByColor`
  - 已消费坐标 key（`_normalAttackQueueConsumed`）
  - `_specialFocusByColor`
  - per-slot row sweep（`_rowSweepBottomRowBySlot` / `_rowSweepCursorBySlot`）
  - 底行缓存（`InvalidateBottomRowCache`）
- `ResetTargetingStateForNewlyOccupiedSlot` 仍只重置**该槽位** row sweep 与对应颜色 special focus，**不清**普通攻击队列（与 Bot 录制口径一致）；同时会清空该槽位 cooldown，避免槽位复用后新入槽首发被历史冷却误延后。
- 运行中禁止为“修回放”在落子或战斗 tick 额外清空 targeting；队列漂移应回到 LoadLevel 是否执行了开局重置排查。

### 2.2.2 下落落地锁与连续加速

- `BlastBlockState.dropLandRemainMs` 是 Sim 规则：块完成真实向下移动后，在 timer 清零前不可攻击，但仍占格并挡住列前沿；回弹动画不计入此 timer。
- `BlastGameLogic.TickCombatInternal` 只在 tick 开始扣减旧锁。攻击、Key、Closing、Pool 等路径随后触发的完整 `BlastEngine.SimulateDropAndRefill`，在 settle/refill/normalize 结束后统一按 runtimeId 的 source/target 登记新锁，因此同一 tick 不会提前扣掉新锁。
- 单段时长由 `BlastDropTimingContext` 决定：`baseDuration * pow(accelerationMultiplier, sequenceIndex)`；连续多行取各段之和。锁存续期间沿用 `dropSequenceIndex`，归零后序号重置为 0。`accelerationMultiplier` 限制在 `(0,1]`。
- `BlastAttackSystem` 的底行候选、普通攻击队列、机会判定和 `SlotAttackOnce` stale-target 校验统一调用 `BlastBoardDropLanding.IsAttackable`。锁住的块继续作为占格存在，禁止看穿攻击上方块。
- Gate 与 Block2x2 按整组锁；Key/普通块新生成块按同列等距虚拟来源轨道的统一向下移动距离锁，Pool 新生成块按对应 Pool 下边缘到目标格的一段锁，避免同列新补块共享单一入口造成视觉重叠；Pool UI 额外按 `boardCellPoolSpawnBottomOffsetPixels` 下移视觉起点但不改变规则时长。Snake shorten、Curtain 类型转换和 Wall 横向流动不产生重力落地锁。Gate 的 close/Advance 动画不写入该 timer。

### 2.3 连线组入槽压缩

- 当 `slots` 中“连续空段不足”但“空位总数 >= 连线组数量”时：
  - 先将现有槽位内容整体左移压缩；
  - 再执行连线组入槽。
- 若空位总数不足则放置失败。
- Stage 候选放入槽位后先进入 `FlyingIn`，`FlyingIn` 归零后才自然变为 `Occupied`。
- `3` 合 `1` 不再由 placement callback 直触发，统一由 `BlastGameLogic.AdvanceSlotStates(...)` 在 tick 末尾判定；`FlyingIn` 期间不参与 `TryMergeSlots` 分组。
- `gameLevel < 3` 时，数据层仍按既有门槛屏蔽 `TryMergeSlots`。
- `gameLevel >= 3` 时，维持原有同色同 `triangle` 满 `3` 自动合并。
- main/temp 只差容器和参与 tick 的时机，规则本身共用同一套 `AdvanceSlotStates -> TryMergeSlots`。
- 槽位可放置语义统一走 `BlastStageController.CanSlotAcceptPlacement(...)`（`IsSlotPlaceable(...)` 为转调），避免在各处直接按 `lifeState` 分叉口径。
- 失败判定/可加载判定共享 `HasLegalPlaceableColumn(...)` 路径，确保“可放置”与“是否死局”不出现语义分叉。

### 2.4 队列与 Pool 解耦规则（含 initialStacks 扣减口径）

- 入口链路：`BlastGameLevelSession.FillQueueFromLevel` -> `BlastBalanceCalculator.Calculate` -> `BlastQueueBuilder.BuildBaseQueue` -> （可选）`ExtractPoolQueuesFromQueue`。
- 原始弹药（raw ammo）不是按 stage 格子数计，而是按候选发射量生成：普通 stage 单元按 20，三角按 40；再叠加 deck override（见 `BlastQueueBuilder.BuildStageColumns/CollectShooterAmmoColors`）。
- `initialStacks` 扣减口径：
  - 普通可清块按 `stackHeight * unitsPerLayer` 计入；
  - Gate 使用 `GateSize`；
  - Pool 成员不进入 `initialStacks`（后续走候补口径）；
  - Snake 额外按 `SnakeSize` 注入；
  - `Block2x2` 使用 `BuildBlock2X2InitialUnitsByCell` 计算分组预算。
- `Block2x2`（initialStacks 侧）：
  - 异色组：每格按 10，整组总 40；
  - 同色组：整组按 `TowerValue` 记预算；同色 companion 不应再走 `+1` fallback。
- 候补（pool reserve）口径：
  - `poolValue = max(0, stack.PoolValue)`；
  - 主玩法队列为 `remainingQueue`（从 `queueBase` 剔除 pool 预留后剩余），不参与动态难度洗牌；
  - Runtime/Bot 必须共用 `Sim/BlastInitialQueueBuilder` 构建初始 `queue/pool`，禁止各自维护 pool 拆队或 difficulty 应用顺序；
  - Pool 2x2 归属按“左下锚点优先 + 单 cell 唯一归属”构建，不再允许滑窗重复识别同一片区域；
  - Pool 颜色来源：
    - 同色 2x2：沿用组颜色；
    - 异色 2x2：必须按 `左下→右下→左上→右上` 四格各自颜色取值，再按同顺序分段拼接候补列表（不是“每格 10”，也不是“全用锚点色”）；
  - 剔除口径与 `balance.poolQueueItems` 一致：按列表顺序在 `queueBase` 中逐个 `IndexOf` 移除对应颜色（同 `ApplyInitialStacks`）；剔除成功的列表按 `左下→右下→左上→右上` 配额切分后合并到数据锚点单 key；
  - 若 `poolQueueItems` 无法全部剔除，回退为 `queueBase` 头部切 `poolValue` 个（`pool2x2_merged_head_slice`）；
  - 守恒：`poolReservedCount + remainingQueue.Count == queueBase.Count`，且 `poolQueuesByAnchor` 内弹量即刚从 `queueBase` 移出的那一批（非合成列表）；
  - `CountPoolReservedUnits` 统计候补总量（合并后等于 `poolValue`）；
  - 主玩法队列只对 `poolExtract.remainingQueue` 做 `ApplyQueueDifficulty(...)`；
  - 校验不变量：`gameplayQueue.Count + poolReservedCount == queueBase.Count`，不满足时走 fallback 空池路径。
- 运行时判定补充：
  - 关卡胜利判定是“盘面可清目标归零”（`RemainingClearTargetBlocks <= 0`），不要求 slot/ammo 归零；
  - 因此“通关时 slot 仍有余弹”不直接代表配置错误，需要结合上述扣减与候补口径一起看。
- Pool 2x2 UI 口径：
  - 四格 `poolQueuesByAnchor` 可异色（仿真数据不变）；
  - UI 整块仅显示 `Pool` 占位图，不按队列队首改色、不铺彩色底块；
  - 剩余弹量读合并后的数据锚点候补（`BlastPool2X2Resolver.GetPoolGroupRemainingCount`）；`Pools[锚点]==null`（已 Clear）视为 0，禁止回落 `PoolQueuesByAnchor` seeded 假剩余。
  - 视觉锚点（左上）由数据锚点（左下）推导，不再用“任意 2x2 全 pool”的滑窗推断。
  - 耗尽清组：`ClearPoolGroup` 先清 `Pools`+`PoolQueuesByAnchor`，再对四格 `ApplyKillClosing`（与 Block2x2 同 Closing 占坑）；UI `PlayPendingKilledCollectVisuals` remap 到视觉锚点播 close，companion ForceRelease。
  - 已 Closing 的 Pool：`ApplyKillClosing` / `ClearPoolGroup` / `RefillFromPools` 不得再次刷新 `closeRemainMs`（空坑在 Closing Pool 下方时每次 Settle/Refill 会重入 Clear，否则计时被刷回满、上方永远不落）。
  - `CleanupDepletedPoolAnchors` 遍历 `PoolQueuesByAnchor` 前必须快照锚点：`ClearPoolGroup` 会 `Remove` 同字典，边枚举边清会在 Bot 并行批跑中抛 `Collection was modified`。
- Pool 2x2 运行时补块口径：
  - 提取阶段已输出单锚点合并队列；`ConsolidatePoolQueuesOnState` 仅兼容旧多 key 存档；
  - `BlastEngine.RefillFromPools` 只从数据锚点 dequeue；同一行多列空位共用一次出队。
  - `GetOrCreatePoolListForAnchor` 只在 live `Pools[锚点]==null` 时从 `PoolQueuesByAnchor` 懒加载；`remaining==0` 不得 `ResetPoolListHead` 重种整表（否则 2x2 同行第二列会把已消费的 `PoolValue` 再吐一遍，破坏守恒）。
  - `SimulateDropAndRefill` 按 `settle → 顶行队列 → Pool 补块` 循环至稳定；每轮补块后清理耗尽锚点，并受最大轮数保护。
  - 锤子清掉 Pool 下方已显示的同色普通块后，新出块拥有新 `runtimeId`，保留不在同一次锤子中再次清除；空坑由上述循环补齐。
  - 仅 pool 关卡：`Pools` 队列用 `PoolListHead` 做 O(1) 队首消费（对齐 `RemoveAt(0)` 语义，避免高频 drop/refill 的列表搬移）。
- Block2x2 归属口径：
  - 与 Pool 一致：stack 标记格为 **左下锚点**，向 **右上** 扩展四格（`BuildMembersFromAnchor`：`y-1` 为上方行）；
  - `coverage` 与 `initialStacks` 预算计算共用同一组 `BuildStackGroups` 结果，避免相邻锚点重复覆盖。
  - 加载时仅 stack 标记格写入 `block2x2Anchor=true`；`NormalizeBlock2x2GroupsInPlace` 只从这些配置锚点归组，避免同伴格被误当作锚点拆成多组（UI 多个大格）。


### 2.5 道具边界（Hammer / Wand）

- 锤子仅消除普通块（`isSpecial == false`），不消除 `Block2x2/Gate/Snake/Objective` 等特殊块。
- 锤子清 Board 后：把被消块 `health` 总和按同色写入候补队列 `State.Queue`；每组最多 `stageCandidateNormalAmount`（默认 20），不足自成一组；整组插在「同色连续 run」组缝上（一次 `Random(removed)` 依次 Next）；不扣 Stage / Slot。补回后会再 `SimulateDropAndRefill`，避免队列已补而盘面空坑未吸。
- 魔棒只基于当前棋盘真实可攻击颜色判断可解性，不承担修正 `Block2x2` 同色化的职责。

### 2.6 Board Closing 占位 + Snake 缩短

- 击杀统一 `BlastBoardClosing.ApplyKillClosing`：`health=0` + `closeRemainMs` 占坑；`TickBoardClosing` 到期清坑后 Settle。
- **占位挡 Settle，也挡列前沿**：不可看穿 Closing 打同列上方；其它列**当前全局底行**上的活块仍可打（不可打到第二行）。
- **统一判断**：存活=`health>0`；占格=`OccupiesBoardCell`；列前沿=`TryGetColumnFrontLiving`（占格挡看穿，Closing 则本列无目标）。
- UI close 仍由 `killedRuntimeIds` 触发（`PlayPendingKilledCollectVisuals`）；Closing 只负责占坑时长，不另开 UI hold。
- Block2x2：`Normalize` / Budget 只服务存活组；Gate 组 ID 在关卡初始化建立且 Settle 后保持稳定（可含 Closing victim 供 Advance）；Snake/Curtain 建组只链存活段。
- Gate：仅 victim Closing（时长=滑动）；到期 Advance；击杀帧 UI 不解绑，Advance 后 `PlayGateRelocateCloseVisual`（解绑→自播滑动→回收）与存活段一起位移。存活段重力/Advance 净位移走统一局部坐标 `PlayGateRelocateVisual`（Head/Body/Tail 同路径）；tween 期间禁止 `SnapTo` 打断。
- Snake：Tail Closing；总攻击数按 `totalBlocks - 1` 个逻辑消除单位分配，余数均匀分摊到前面的单位，最后一个单位对应最后两个 cell 一起 Closing；`BeginOrRefreshShorten(group, fromEliminated)` 只写几何 from；计时看块 `closeRemainMs`。
- Key：不属于 Slot 的可攻击目标；仅在 Board 前排与 Stage 前排 Lock 同时就绪时配对。配对当 tick 立即推进 Lock 所在 Stage 列；Key/Lock 动画只消费配对事件，不阻塞数据。`PendingUnlock` 由 `TickBoardClosing` 扫描，仅兼容清理旧的在途数据。
- Bot：`ResolveClosingDurationMs` fold→~0 则同帧清坑。
- 终局：`HasPendingClosingOccupancy` / `HasPendingDropLanding` 仅用于 `ShouldDeferFailureForTransientState`，不改变攻击机会门。
- 表现层见 `Gameplay_Flow_Logic.md` §2.0.1 与 `GM_Board_Flow.md` §5。

## 3. 调试与验证锚点

- Board/Stage 时序流程图：`Doc/MainGame/GM_Board_Stage_Flow.md`
- 主流程编排：`Doc/MainGame/Gameplay_Flow_Logic.md`
- 回放一致性验证：`Doc/MainGame/Blast_Replay.md`

## 4. 类功能定位

| 类/文件 | 功能 | 路径 |
|---|---|---|
| `BlastAttackSystem` | 攻击目标选择、发射推进、命中与销毁事件；`ResetAllCombatTargetingState()` 供 `LoadLevel` 开局清空 targeting | `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.cs` |
| `BlastSpecialTargetSelector` | 特殊目标筛选算法：类型优先级（Objective/Snake/Gate/Block2x2）+ focus + 击杀代价 + 坐标 tie-break | `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.Targeting.cs` |
| `SlotRowSweepSnapshot`（struct） | Bot clone/lookahead 用的五槽 row sweep 快照，保存每个 slot 的 bottom row 与 cursor | `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.cs` |
| `AttackResult`（struct，SlotAttackOnce 输出） | 单次攻击结果：hitPositions、killedPositions、deferredRemovals、collectable 计数 | `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.cs` |
| `BlastEngine` | 下落补块、特殊块结构处理；Block2x2/Gate 刚性整组下落见 `BlastEngine.RigidGroups`；Settle 跳过 Closing 占位 | `Assets/GameModule/GameMain/Script/Sim/BlastEngine.cs` |
| `BlastEngine.RigidGroups` | Gate/Block2x2 整组 `CanMove*Down` / `Move*Down`；`CollectGateGroupMembers` / Closing 门控 | `Assets/GameModule/GameMain/Script/Sim/BlastEngine.RigidGroups.cs` |
| `BlastBoardClosing` | Board Closing 占位 Begin/Tick/清坑；并扫 Key PendingUnlock | `Assets/GameModule/GameMain/Script/Sim/BlastBoardClosing.cs` |
| `BlastSnakeShortenResolver` | 蛇缩短几何 from/elim；Closing 计时跟块 `closeRemainMs` | `Assets/GameModule/GameMain/Script/Sim/BlastSnakeShortenResolver.cs` |
| `BlastStageController` | 候选入槽、槽位推进、连线组处理 | `Assets/GameModule/GameMain/Script/Runtime/BlastStageController.cs` |
| `BlastQueueBuilder` | 队列构建、Pool 预留与扣减 | `Assets/GameModule/GameMain/Script/Sim/BlastQueueBuilder.cs` |
| `BlastDifficultyApplier` | 队列难度应用（split/reverse/overflow） | `Assets/GameModule/GameMain/Script/Sim/BlastDifficultyApplier.cs` |

维护规则：规则层新增或替换核心类时，需同步本表与总索引文档。
