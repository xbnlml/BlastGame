# Slot Area Logic（槽位区域）

本文维护 Main / Temp Slot 的数据—视图映射、动物生命周期、关闭与压缩表现。主流程何时放置、攻击或结算见 [Gameplay_Flow_Logic.md](Gameplay_Flow_Logic.md)；失败续命的业务判定与迁移入口见 [Fail_Revive_Logic.md](Fail_Revive_Logic.md)。

## 1. 视图与生命周期

- 运行期视图编排：Controller `RequestRuntimeViewRefresh` → Presenter `RefreshRuntimeViews`（Board → Slots delta → Stage delta → Effects）。Controller 不直调三区 View 的 Bind/Apply/Refresh。
- `BlastGameTransientTaskRegistry` 是局内临时异步任务的统一取消入口，当前覆盖 detached close、fail-revive 延迟消费和 Stage PowerUp reveal 延迟恢复。`ResetViewsForRebind` 在回收三区前调用 `CancelAll()`。
- detached close 启动时使用当前 registry token；close / fly 的等待立即收到取消，旧任务不再执行 release 或 release-completed 回调，`ReleaseAllActive` 只回收当前活跃对象。
- 槽位“可放置”语义入口为 `BlastStageController.CanSlotAcceptPlacement(...)`，`IsSlotPlaceable(...)` 只转调该入口，避免直接按 `lifeState` 分散判断。
- `SlotVisualState` 是槽位渲染快照（`lifeState + ammo`）；`RefreshSlotLinkEffects(...)` 必须把 `temp` 区纳入重建。连体迁移时 `UpdateSlotLinkBetween(...)` 优先复用 `adoptedLinkView` 并移除旧 key 绑定。

## 2. Main / Temp 槽位规则

- `ApplyTempPieceVisual` 清空时仅在 Cell 仍挂动物才启动 close，且不提前写入 empty `visualHash`（失败后可在下帧重收）；empty hash 命中但 Cell 仍挂动物时禁止 early-out。
- `TryPromoteDepletedSlotsToClosing` 按主槽位计数维护 `pendingIncoming`；Presenter 在放置开始、完成和中断时同步通知 Controller，并保留 SlotsView 的显示侧计数供过渡渲染。
- `BlastSlotPiece.runtimeId` 是槽位数据身份：新 Stage 放入分配 ID，fail-revive 迁移及快照/预测 clone 保留 ID，Main 合成保留 target ID 并记录 source IDs。Temp packed 压缩只改变布局映射，不改变动物身份。
- `BlastSlotsView` 同步 Cell 时重建 `runtimeId → Cell / Spine / 逻辑槽位` 注册表；注册表仅读取已同步的 `CellPool.Cells`，重建期间禁止触发会 `SyncCells` 的 Temp Cell 查询。
- Main 逻辑索引等于可视索引；Temp 逻辑索引须先映射为 packed 表现座。所有逻辑槽→Cell 转换由 `TryDetachAnimalFromLogicSlot` 收口，调用方只能使用其返回的可视索引访问 CellPool。

## 3. Close、合并与回收

- Temp close 在 Closing 边沿同时捕获 `runtimeId` 与 Spine；异步执行前由注册表验证 ID 仍绑定原 Spine，否则取消，不得按已压缩的 Temp 座位退化 detach。Main close 同样在 Closing 边沿捕获 ID 与 Spine。
- Cell 仅在 Spine `AdoptAnimal` 实际落入 Slot 时绑定 ID；进入 detach / close / merge 或回池时立即清空。`ReleaseAnimal(true)` 必须先以 `runtimeId + 当前 Spine` 校验并发起 close，成功后注销注册表再清空 Cell；close Spine 仅由 detached 动画链路回收。
- Slot merge 计划携带 `MergeTargetPieceRuntimeId` 与 `MergeSourcePieceRuntimeIds`；执行器只可用 source ID 从注册表 detach，槽位索引仅作动画位置数据。`SlotCell.BeginRecycleToPool(...)` 同步回收触碰该 slot 的连线。
- 已移除未使用的 `SlotCloseFly` UI 动画计划入口；close 统一由 SlotsView 的 ID 校验后交给 detached Spine 飞行链路，禁止只携带 `slotIndex/Spine` 的旧路径。
- 切场解绑 Slot 飞行层调用 `UnbindSlotsCellRootDown()`；不得用 `BindSlotsCellRootDown(null)` 清理。Board→Slot 攻击飞按 `SourceSlotIndex` 挂主/临时 `CellRootDown`。

## 4. Temp 区收缩

- Closing 边沿先关闭正确视觉座并 `NotifyTempCloseStarted`；延迟 A 内 Closing 仍占表现座，禁止提前 densify 或旁路 `TryPlayTempCompactionMoves`。
- t0+A：densify 后按视觉座横移幸存 Occupied；横移开始+B：Seat/Dianzi close 只播一次；Seat 完+C：缩 Desk。收缩期间攻击到达不得重刷 Temp 进度条。
- Temp close 必须携带 Closing 边沿捕获的动物实例，并只 detach 该实例，防止压缩/补入后关闭新动物。close 飞出先取得 Temp Cell，再校验 CellPool 边界，不得用压缩后的逻辑数量否掉旧视觉座。
- A/B/C 和压缩飞行 Linear 配置位于 Fail Revive Motion。
- `BlastSlotDeskRootView` 的 Temp Desk appear 是本局一次性表现：异步续命序列与常规 `SetTempVisibleCount(0→正数)` 共用同一已播放标记，禁止任一路径重播 appear（其首帧会把 Desk alpha 写为 0，重复播放会闪）；`HideImmediate` 等临时收起不重置标记，仅 `RecycleForReload` 的关卡回收重置。
- `EnsureMainSlotCellsReady` 只补齐/校正 Main Cell，不得把 CellPool 收缩到 `mainCount`；已有 Temp Cell 承载的是仍存活动物，第二次 fail-revive 扩容前必须原样保留，禁止经尾部回收误播 close。
