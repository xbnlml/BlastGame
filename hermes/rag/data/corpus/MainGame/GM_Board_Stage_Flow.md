# Blast Board / Stage / Slots 主流程


## 职责与所有权

- `BlastGameViewPresenter`：三大区域刷新编排者，统一管理初始化、增量刷新与重绑清理顺序。
- `BlastBoardView`：仅负责盘面展示，不改玩法状态。
- `BlastStageView`：仅负责候选列展示与输入承接，不做玩法判定。
- `BlastSlotsView`：仅负责主槽/临时槽展示与状态可视化，不定义可放置/可攻击规则。

## 协作边界

- 运行期刷新入口统一为 `Presenter.RefreshRuntimeViews`，调用顺序固定为 Board → Slots → Stage → Effects/HUD。
- 全量初始化（`BindInitial*`）仅用于 `LoadLevel`/重绑；运行期必须走 delta 或 reconcile。
- 放置流程由 Controller/Sim 先完成数据规划，UI 只消费结果，不通过动画回调反推状态。
- close/flying/merge 等过渡态收口后，后续判定仍以数据状态为准。

## 生命周期分层

- 生命周期入口：`LoadLevel -> ResetViewsForRebind/RecycleForReload -> InitLevelViews -> BindInitial*`。
- 运行期：`FixedUpdate/道具` 驱动 `RefreshRuntimeViews`，禁止用全量初始化替代增量刷新。
- 统一清理：切场、回退、重载都由 Presenter 触发区域回收；回收前必须清理回调、动画与临时引用。

## 适用范围

说明局内三大区域如何从运行态刷新到视图。玩法数据规则见 [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md)。

## 1. 区域职责

- Board：展示 `BlastGameState` 的盘面和特殊结构。
- Stage：展示候选并接收列点击。
- Slots：展示正式槽、临时槽和槽位状态。
- Presenter：按状态变化协调三大区域和 Effects/HUD。

## 2. 加载与运行期刷新

```text
LoadLevel
  → Presenter.BindInitialViews
  → Board / Stage / Slots 全量初始化

Runtime state change
  → mark dirty / build delta
  → Presenter.RefreshRuntimeViews
  → Board → Slots → Stage → Effects / HUD
```

- 全量初始化只用于进关和回退恢复。
- 运行期只消费数据变化和增量，不能从 UI 反推玩法状态。
- Board 位置变化必须先完成，再刷新依赖锚点的 Slots、Stage 和连线效果。

## 3. Stage → Slot 放置

1. Stage 接收列点击并检查放置流门控。
2. Controller / Sim 先完成候选和槽位数据规划。
3. Presenter / Effects 执行动物、连线和落位表现。
4. 落位结束后由状态机收口 `FlyingIn`、`Merging` 等暂态。
5. 后续战斗判断只读取已收口的数据状态。

动画失败不能回滚已经成功的数据状态；视图只能跳过表现并等待下一次同步。

## 4. 生命周期边界

- 关卡重载、回退、退出时由 Presenter 统一解绑和回收。
- 对象池对象回收前必须清理回调、动画和临时引用。
- 新旧 Piece、Animal、Cell 的生命周期必须分离，不能按 slot index 误回收。
- 连线效果属于视图表现，不能作为合成、攻击或可放置判定依据。
- Stage 候选连线（`BlastLineEffectView`）：端点 Special 由 `triangle` 决定；`secret && displayRow>0` 时显示对应 PointMark、隐藏 PointColor，线段色固定 `#7C8A95`；进前排揭晓后切回 PointColor + cell 色；回收 `Hide` 须隐藏全部 Mark 并恢复 PointColor，避免池复用残留。

## 5. 代码入口

| 问题 | 入口 |
|---|---|
| 三大区域刷新 | `BlastGameViewPresenter.RefreshRuntimeViews` |
| Board | `BlastBoardView.BindInitialState` / `ApplyRuntimeDelta` |
| Stage | `BlastStageView.BindInitialCandidates` / `ApplyCandidateDelta` |
| Slots | `BlastSlotsView.BindInitialSlots` / `ReconcileFromLogicState` |
| Stage 点击 | `BlastGameController.Stage` |
| 放置流 | `BlastPlacementFlowCoordinator` / `BlastPlacementFlowState` |
| 动物动画 | `BlastStagePlacementAnim` / `BlastStageAnimalView` |
