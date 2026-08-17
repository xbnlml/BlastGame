# Blast Board 区域主流程


## 类职责分层

| 类/文件 | 职责 |
|---|---|
| `BlastBoardView` | Board 刷新主循环、运行态增量应用、生命周期回收入口 |
| `BlastBoardLayoutManager` | 盘面排布与窗口缩放，提供布局语义 |
| `BlastBoardCellPoolManager` | BoardCell 池化生命周期管理 |
| `BlastBoardBlockVisualResolver` | 规则块到视觉数据映射（类型、尺寸、锚点、层级） |

## 协作边界

- Presenter 产生边沿/dirty，Board 仅执行渲染；不从 Board 反写玩法状态。
- 运行期刷新语义区分：`RebuildFromCurrentState`（显式全量例外）与 `ApplyRuntimeDelta`（常态增量）。
- `SetState/SetRelocateMoves/NotifyHitPositions` 作为边沿输入，不与万能 refresh 混用。
- 命中/关闭表现只消费 Sim 输出，不在视图层新增判定规则。

## 生命周期与池化边界

- `RecycleForReload` 负责掐断回调并统一入池。
- 新出池 cell 走初始 visual 绑定；复用 cell 仅更新必要数据，避免重复初始化。
- Spine 类与 Image 类关闭回收路径分离，但都必须遵守“先解绑后回收”。

## 适用范围

说明 Board 的数据、刷新、对象池和特殊块主流程。动画资源表与具体组件参数不属于本文。

## 1. 数据流

```text
BlastGameState
  → BlastBoardData / VisualData
  → BlastBoardView
  → BoardCell / special visual
```

- Sim 产生盘面状态和关闭/下落结果。
- `BlastBoardCellVisualDataBuilder` 将运行态转换为展示数据。
- `BlastBoardView` 负责初始绑定、增量刷新、重建和回收。
- Board 不修改玩法状态，不决定攻击、合成或胜负。

## 2. 刷新链路

- 加载和回退：`BindInitialState` / `RebuildFromCurrentState`
- 运行期：`ApplyRuntimeDelta`
- Presenter 先处理 Board，再处理依赖 Board 锚点的 Slots、Stage 和 Effects。
- `RecycleForReload` / `Release` 负责清除回调、动画和池对象。
- 增量态已有 cell：未在播**第一段掉落**时须 `AttachCellToRuntimeSlot` 纠到当前逻辑格；禁止只靠「pending relocate 列表」跳过纠位（Key 清坑后 relocate 漏播会留空位）。回弹段不挡纠位判定（`IsRelocateMotionProtected` 只认 `IsBoardDropActive`），但 `SnapTo` 仍认 `IsBoardMotionActive` 避免打断回弹。
- 增量态新补入 cell（`isNewCell`，无上方来源）：普通队列块由 `PlayNewFillDropVisual` 使用同列等距虚拟来源轨道落入目标格；Pool 出块则从对应 Pool 显示块的下边缘开始，横向强制对齐目标列，并按 `boardCellPoolSpawnBottomOffsetPixels`（默认 20）下移起点，禁止多块重叠在同一入口或 Snap 原地闪现（锤子大批补块同口径）。
- BoardCell 落位：先挂 `BoardRow_*` 再 Snap 行内坐标（`SnapCellToVisibleRow`）；禁止在 `boardLayoutRoot` 下直接 Snap 行内 y=0。
- Stage 清空后的玩法区域加速：`BlastGameController.MarkPlacementFlowAttackReadyAndComplete` 在 `CountActiveCandidates(Candidates) <= 0` 时开启 `BlastGameplayAreaSpeed`；倍率来自 `BlastUIRuntimeConfig.gameplayAreaSpeedMultiplier`，默认 `2x`。仅影响 BoardCell 位移、BoardCell/Block2x2 Spine 和 Board→Slot 攻击飞行，下一次 Stage 放置流开始时恢复 `1x`；关卡加载、重启和场景切换也会强制恢复 `1x`。不使用全局 `Time.timeScale`，不影响弹板出现及其他场外 UI 动画。Slot 空位耗尽不代表 Stage 清空，禁止作为触发条件。
- **下落两段式（普通格）**：
  1. 第一段掉落：普通位移使用 `boardCellDropTween` 的时长/Ease；带 `DropRows` 的连续 relocate 改为按 `BlastDropTimingContext` 将路径拆成连续逻辑段，每段使用 `baseDuration * multiplier^sequenceIndex`，同列共享本波最早段序号和段速度，不再把多行压成一个独立直线 Tween。来源块在可视区外时也必须按 `SourcePos → TargetPos` 创建 cell 后播放 relocate，不能被主刷新误判成新补块；连续 relocate 时从当前视觉位置续飞，禁止 `DOKill` 后写回旧 `fromPos`；换 `BoardRow_*` 用 `SetParent(..., true)` 保世界位置。
  2. 第二段回弹：列内全部掉落 token 结束后，对该列可见普通格同时回弹。配置：`boardCellDropReboundCurve`（t→本地 Y 像素）、`boardCellDropReboundDuration`、`boardCellDropReboundDecay`。底行=`BoardY` 最大，振幅 `heightScale * decay^i`（i 从底往上）。
  3. 第一段时长与 Sim 共用 `BlastDropTimingContext`：`baseDuration * pow(accelerationMultiplier, sequenceIndex)`，连续多行按每行几何时长求和；`BlastBoardRelocateMove` 携带 Sim 计算的行数、起始序号和毫秒时长，避免 UI 提前或滞后于不可攻击窗口。`accelerationMultiplier` 默认 `0.9`，不使用 MaxDuration 封顶。
  4. 回弹高度：`heightScale = Lerp(oneRowScale, maxScale, heightCurve.Evaluate(t))`，其中 `t=saturate((accumRows-1)/(fullStrengthRows-1))`。配置：`boardCellDropReboundFullStrengthRows`（满幅参考行数）、`boardCellDropReboundOneRowScale`（一行初始系数，默认 0）、`boardCellDropReboundHeightCurve`（默认 Linear）、`boardCellDropReboundMaxScale`。UI 走 `ResolveBoardCellDropReboundHeightScale`；`BlastDropTimingContext` 仅 Linear 对齐默认口径。回弹不延长 Sim 的 `dropLandRemainMs`。
  5. 列 token：`BeginColumnDropMotion` 先登记再开 tween；`OnComplete`/`OnKill` 均结束自身 token；新掉落先 `CancelColumnDropRebound` 恢复未移动格静止位。Gate 使用同一第一段时长但不参加普通列回弹，Snake 不参加普通列回弹。
  6. `ResetRuntimeState`/`RecycleForReload` 先 `InvalidateDropMotionEpoch`，旧回调不得再触发回弹。
  7. 新补块使用逻辑虚拟 `sourceY=-1`，与 Sim 的落地锁和 UI 起点一致；掉落锁期间攻击飞点取 cell 的逻辑 rest 世界坐标，不能追随半空视觉位置。
- `startRow` 只按盘面 `Height` 计算，队列预览不参与棋盘补块。
- `AssignCellToVisibleSlot`：覆盖槽位时，仍在册或 `_recyclingCells` 中的格只让槽、不 `ForceRelease`；仅孤儿回池。下落占槽误杀 close/活格会导致第一行空且 spine 消失。
- Base 离开当前类型：`ClearBaseVisualImmediate` 须将 Image 视觉回 `BlastBoardImagePool` 并关 `blockVisual`；普通块不再使用 Spine skin/动画。
- Board→Slot 攻击飞行（普通底块 Image / Block2x2 租用 Image / `BoardCellAttackFlyVisual`）挂层走 `UIGameMainEffectLayerController.ResolveBoardToSlotFlyLayer()`（优先 `BlastSlotsView`/`SlotDeskRoot.CellRootDown`，未绑定则 `BoardViewUp`）；`AttachKeepingWorld` **禁止** `SetParent(null)`，否则视觉会掉到场景根离开 UI。`BindViews` 时 `BindSlotsCellRootDown`。Board 区仅 close/回收不飞向 Slot 的 Image 仍挂 `BoardViewUp`。Objective 金币飞（Slot→Board）仍挂 `BoardViewUp`，命中态金币用 `BringObjectiveAttackCoinToFront` 置于同层罐子之上，发币 Slot 小动物挂层不变。

## 3. 特殊结构

Board 只展示以下结构的当前状态，规则由 Sim 负责：

- 普通块与攻击命中；
- Gate；
- Key / Lock；
- Objective；
- Snake；
- Block2x2 / Pool。

特殊结构发生下落、关闭或缩短时，数据先更新，视图再按状态变化表现。

Objective 视图约束：

- 同为 Objective 时 `EnsureSpinesForData` 必须 keep spine（禁每次 Sync `Release`+重生）。
- jar 受击播 `res_n`，Complete 后强制 `idle_n`；升级 `DOScale` 到阶段比例并保持到 close，Release/回池清零。
- 自首次 `res_n` 起至 close：`ObjectiveSpineLife` 为真源——`Anchored`（锚点）→ `EffectLayer`（挂 `BoardViewUp`，cell 仍拥有）→ `DetachedClose`（`ClearSpineRef` 后由 close 回调 `BlastBoardSpinePool.Release`）。命中态进入 `EffectLayer` 使用 `AttachObjectiveHitSpineToBoardViewUp` 沉到 `BoardViewUp` 同层底部；Objective 金币出池后使用 `BringObjectiveAttackCoinToFront` 置顶，因此金币盖住罐子但不改变 Slot 小动物层级。close 仍使用通用 `AttachToBoardViewUp` 置顶。cell 只 `ReleaseOwnedObjectiveSpine`；`DetachedClose` 时 `ResetRuntimeState` 只 `ForgetDetachedObjectiveSpineLife`，不二次入池。
- `EnsureSpine` 在 `EffectLayer` 禁止拉回 `ObjectiveSpinePos`；`LateUpdate` 仅 `EffectLayer` 跟随锚点；阶段缩放按 life 换算 localScale。
- 击破奖励飞币起飞前子币须 inactive；CoinNum `jingdu_tuchu` 新到达打断并合并到最新 target。
- CoinNumTxt：金币 `>0` 为 `<sprite=0> N`；`0` / Reset 为空串（不显图）。

## 4. 对象池边界

- 出池时初始化当前状态和视觉数据。
- 回收时清理动画、回调、临时引用和 Spine 状态。
- 不允许用旧 Cell 或旧 Spine 引用承载新 Piece。
- 强制重载、回退和退出必须执行统一清理。

### 4.1 BoardCell Shadow

- 普通块预设首子名 `Shadow`，Spine 类预设兼容旧名 `SpineShadow`；逻辑集中在 `BlastBoardSpineShadowLogic`。
- 正下方存活块（`health>0`，Closing 不算）挡阴影；出池 / 每帧 Refresh 末 `SyncAllSpineShadowsFromState` 按占格重同步（允许开→关）。
- 下方格 **close / 强制回收** 时 `NotifyAboveOfLeaving` 立刻开上方阴影；**下落/位移不通知**（整列落下后下方仍可能挡着，避免闩死误显）。
- Spine 回池 `ResetOnRelease` 强制关阴影。

## 5. 特殊块视图口径

### 5.4 Key / Lock

- Sim：配对当下 Key `RemoveBlock`、Stage `AdvanceCandidateColumn` 与 `SimulateDropAndRefill` 同步完成；Board/Stage 数据不等待 Key/Lock 动画。`PendingUnlock` 仅兼容清理旧的在途数据。
- 两种到达顺序都要配对：① Key 已在 Board 底行、Lock 后到 Stage 前排（`TryResolveAndPresentKeyLockPairs` / TickCombat）；② Lock 已在前排、Key 后落到 Board 底行（TickCombat Pair×3）。
- UI：`PrepareKeyLockPairVisuals` → Key 进 `killedRuntimeIds` → `PlayDetachedKeyCloseVisual`（先解绑回收 cell，KeySpine 挂 StageViewUp 自飞；飞行 tween/回调须局部持有，禁挂 `_keyFlyTween`）。
- 空位：Key cell 已回收但上方不落 → 查 `ApplyRuntimeDelta` 是否对已有 cell 漏 `Attach`；`IsRelocateMotionProtected` 只认 `IsBoardDropActive`（回弹不挡纠位/命中刷新）。

## 6. 代码入口

| 问题 | 入口 |
|---|---|
| Board 初始绑定 | `BlastBoardView.BindInitialState` |
| Board 增量刷新 | `BlastBoardView.ApplyRuntimeDelta` / `PlayNewFillDropVisual` |
| 展示数据转换 | `BlastBoardCellVisualDataBuilder` |
| 关闭/下落结果 | `BlastBoardClosing` / `BlastEngine` |
| Key/Lock 配对 | `BlastKeyLockResolver` / `TryResolveAndPresentKeyLockPairs` |
| Board 生命周期 | `BlastBoardView.RecycleForReload` / `Release` |
| Board→Slot 攻击飞挂层 | `UIGameMainEffectLayerController.SlotsCellRootDown` / `AttachToSlotsCellRootDown` |
| 三大区域顺序 | `BlastGameViewPresenter.RefreshRuntimeViews` |
