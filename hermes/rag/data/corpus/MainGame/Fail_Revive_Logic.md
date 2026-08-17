# Fail Revive Logic（失败续命）

本文维护失败续命的判定、付费确认与 Main Slot → Temp Slot 迁移。Slot 区的通用渲染、关闭与压缩规则见 [Slot_Area_Logic.md](Slot_Area_Logic.md)；Fail Offer 商品规则见 [PlayOn_Offer_Logic.md](PlayOn_Offer_Logic.md)。

## 1. 判定与确认

- `EvaluateRunState` 使用纯判定 `EvaluateContinueState(...)`：输入逻辑快照（remaining / placementFlow / hasUsableAmmo / canLoad / softLock / failRevive 状态），输出 `CanContinue + LoseReason + 是否弹 fail-revive`；前者只编排弹窗与 `EnterLoseState`。
- 失败前按“有弹药且颜色可命中当前目标”判断主槽与已解锁临时槽。Stage→Slot 放置未到 AttackReady，或 `ShouldDeferFailureForTransientState` 为真时，暂缓失败判定。
- 确认窗为 `UIGameContinueView`。`FailOfferModel.Instance.IsUnlocked()` 决定是否展示 `appear2` + `SalePanel` IAP；`BuyBtn` 走金币复活。成功后关窗播 `close1|2`，再 `TryConsumeFailReviveTempSlots(spendCoins: false)` 只腾槽；有礼包展示时点 close 记 FailOffer 拒绝，金币复活不记拒绝。
- `UIGameContinueView` 在续命判定通过后，经 `OfferFailRevivePromptAfterDelayAsync` 延迟 1 秒打开；任务由 `BlastGameTransientTaskRegistry` 管理，重载/切场时 `CancelAll`。
- 判定同时确认当前与上一帧均没有逻辑子弹，避免攻击飞行刚结束的过渡帧提前弹窗。

## 2. Main → Temp 迁移表现

- `BlastSlotsTempAreaPresenter` 收口视觉顺序：本局首次使用 Temp 时 `BlastSlotDeskRootView` 播 DeskRoot appear（冷启动先关根、零宽再激活，Seat/Cell 由 appear 序列掌控）；等待 `ResolveFailReviveTempDeskAppearToChildDelaySeconds()` 后，从左到右成对播放 Seat/Dianzi appear；完成后腾位动物依 `ResolveFailReviveTempAnimalFlyIntervalSeconds()` 依次起飞。异步续命序列与常规可见数刷新共用一次性 Desk appear 标记；桌面即使曾缩到 0，后续追加也只走 idle/宽度变化，不重播首帧 alpha=0 的 appear；关卡回收后才重置标记。
- 飞行轨迹复用 `ResolveTempSlotFailReviveFlySettings()`；配置在 Fail Revive Motion。收集从主槽尾部取单位，写入 Temp / 起飞前按 `SourceSlotIndex` 升序。
- Desk 展示期间源槽动物仍挂在 Cell；起飞瞬间才 detach 并收进度条，目的地进度条只在 Adopt 后出现。`_failReviveHeldSourceSlots` 阻止 `SyncMainSlotFromLogic` 与全量刷新覆盖空位。
- 表现完成前 Controller 拦截 Stage 点击并锁住 Temp 攻击；完成意图在下一次 `FixedUpdate` 消费后解锁。飞完若 Temp 已空或 `TryGetTempSlotCell` 失败，调用 `PlayDetachedCloseInPlaceAndReleaseAsync`，不得 Adopt 到空槽。
- 飞入 Temp 落地 `AdoptAnimal` 必须直接携带迁移 piece 的 `runtimeId`；飞行/压缩期间不得通过 packed 视觉座反查 ID。Controller 会先将迁移单位写入 `tempSlots`，Presenter 统计旧座时必须按本次迁移 ID 排除新单位，不能依赖 `_tempPackedPieces` 表现缓存；`Closing` 已由 detached close 动画接管，不占可见 Temp 座。故旧 3 个活体 + 新 2 个必须落为 0–4，不能因隐藏 Closing 条目或已写入的新条目把飞行目标算到 5 号以外。
- 第二次 fail-revive 扩容前调用 `EnsureMainSlotCellsReady` 时必须保留现有 Temp Cell；该入口只保证 Main Cell 就绪，不能先把 CellPool 收缩到 Main 数量再扩容，否则旧 Temp Cell 会走带 close 的尾部回收，造成数据仍在但动物被误关。
