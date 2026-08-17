# 运行期 UI 刷新合并计划（修订版）

## 目标与边界

目标是消除运行期“数据未变仍调用 Presenter”的刷新，并将同一渲染帧的多次**状态同步请求**合并为一次。

- `BlastGameController` 只聚合运行期状态同步请求。
- `BlastGameViewPresenter.RefreshRuntimeViews` 仍是 Board / Slots / Stage / 连线 Effects 的唯一状态同步入口。
- 不把道具 Tween、攻击飞行、HUD 数字、弹窗等即时表现强行并入该入口；它们有自己的时序，不能为了合并刷新而延迟。
- LoadLevel / 回退重绑继续使用 `InitLevelViews`，不纳入本计划。
- 不改 Sim、Slot View、Stage View 的渲染模型；Reveal 行距 Tween 也不在本次重构中改时序。

## 已确认的问题

### 1. 非 Playing 状态会持续提交空请求

`FixedUpdate` 在 `HandleNonPlayingUpdate(...)` 返回后无条件调用 `RequestRuntimeViewRefresh()`；而该函数对所有非 Playing 状态都返回 `true`。因此结束、弹窗等待等阶段会每个 FixedUpdate 进入 Presenter，即使 Board / Slots / Stage / Effects 都没有变化。

### 2. Effects dirty 当前存在“消费后重新置脏”的风险

Controller 的 `ComputeNeedEffects(...)` 会消费 Presenter 的 `_forceEffectsRefreshRequested`；随后 `RefreshRuntimeViews(..., needEffects)` 又调用 `RequestForceEffectsRefresh()`。一次 Effects 请求可能因此在下一 Tick 再次触发请求，而不是在本次真正刷新 Effects 后结束。

### 3. 同帧多请求仍会立即进入 Presenter

`RequestRuntimeViewRefresh` 当前立即构建 Board relocate delta 并调用 Presenter。多个 FixedUpdate 或道具回调落在同一渲染帧时，会重复计算 hash、重复设置 Hammer 状态，并可能重复检查 Stage / Slots。

## 设计

### A. 最小 pending 状态（Controller）

不新增事件总线、状态机或 `refreshKind` 返回协议。保留现有 Presenter 的 Board dirty、Slots hash、Stage version 分区门控；Controller 仅保存调用参数的并集：

```csharp
bool _runtimeRefreshPending;
IReadOnlyDictionary<int, Vector2Int> _pendingBoardBeforeStep;
bool _pendingAttackDriven;
bool _pendingBoardDataChanged;
bool _pendingHadHits;
bool _pendingForceRuntimeBoardRefresh;
bool _pendingNeedEffects;
```

- bool 一律按 OR 合并。
- Board 快照只在本批次第一次收到攻击快照时保存：它代表本帧连续攻击前的最早位置；Flush 时以当前 `State` 计算最终 relocate。
- 非攻击请求不得覆盖已保存的攻击快照。
- 关卡重载、回退重绑、解绑视图时清空 pending，禁止旧局的请求在下一帧落地。

### B. Request 只观察并合并，不渲染

`RequestRuntimeViewRefresh(...)` 不再构建 relocate，也不调用 Presenter。

它只做两件事：

1. 记录 Board 相关参数与攻击快照。
2. 在**请求时**计算并 OR 到 `_pendingNeedEffects`。

Effects 需要在请求时捕获，因为 `_hadBulletsLastFrame` 是 Controller 的边沿状态；不能等到 LateUpdate 再用最终 `_bullets` 倒推“本帧是否刚结束”。

`ComputeNeedEffects(...)` 改为只处理 `hadHits / bullets / _hadBulletsLastFrame`，不再消费 Presenter 的强制 Effects 标记。

### C. Presenter 自己消费 Effects dirty

`RequestForceEffectsRefresh()` 仍是 Presenter 的 dirty 生产入口。

在 `RefreshRuntimeViews(...)` 内：

```text
needEffects = Controller 本批次捕获的边沿
             OR Presenter.ConsumeForceEffectsRefreshRequested()
```

若 `needEffects` 为真，当前批次直接调用 `RefreshEffectsAfterLayout(slots, candidates)`；不得再次调用 `RequestForceEffectsRefresh()`。

这样 Effects dirty 只有“生产 → 本次消费 → 清除”一条路径，不会反馈成下一 Tick 的永久刷新请求。

### D. LateUpdate 单次 Flush

新增 `LateUpdate` 与 `FlushRuntimeViewRefresh()`：

```text
pending == false
  → 不进入 Presenter

pending == true
  → 复制并立即清空 pending
  → 用复制的最早攻击快照 + 当前 State 构建 relocate delta
  → 用当前 Slots / TempSlots / Candidates 调用一次 RefreshRuntimeViews
```

必须“先清空、后调用 Presenter”。若 Flush 内部或回调期间又产生请求，它属于下一帧，不能污染当前批次。

### E. 非 Playing 改为按 dirty 请求

将 `HasPendingFixedUpdateViewChanges(...)` 扩展为通用的 `HasPendingRuntimeViewChanges(...)`，并纳入 `_boardDirty`、Stage version、Slots hash、Effects dirty。

非 Playing 分支执行完胜负弹窗检查、循环推进和 Board safeguard 后，只在该查询返回 `true` 时调用 `RequestRuntimeViewRefresh()`；不再因为“当前不在 Playing”本身请求刷新。

正常 Playing 分支继续沿用该查询与 `hasBoardDataDelta / bullets` 的语义，确保攻击飞行、刚结束子弹和数据边沿不会漏刷。

### F. Reveal 与直接 UI 表现不改时序

当前 `RunStagePowerUpRevealTransition` 启动 `SetMagnetMode` 的布局 Tween 后立即结束 Controller 的 transitioning 标记；`StageView.SetMagnetMode` 也没有完成回调。

因此本计划不承诺“Tween 完成后再消费 Stage”，也不把 `SetMagnetMode` 移入 Flush。道具 Reveal 的行距 Tween 保持原入口和原时机；它不是普通数据同步刷新。

若后续要做 Reveal 期间的 Stage defer，另立任务：先为 Stage 行距 Tween 建立可靠的完成回调，再讨论延后 Stage delta。

## 实施顺序

1. 用 CodeGraph 列出 `RequestRuntimeViewRefresh` 调用点，并按攻击、道具、非 Playing、Key/Lock 分类；确认调用方没有依赖同步执行后的 UI 结果。
2. 在 Controller 增加 pending 字段、清空方法与 `LateUpdate` Flush；先保持 Presenter 签名不变。
3. 改造 `RequestRuntimeViewRefresh` 为纯聚合，并保留 Effects 边沿捕获。
4. 修正 Presenter 的 Effects dirty 消费：本次真正刷新，禁止消费后再置脏。
5. 将非 Playing 的无条件 Request 改为 `HasPendingRuntimeViewChanges(...)` 门控。
6. 清理旧 repeated-frame 诊断；仅在开发模式记录 `requestCount / flushCount / effectsConsumed`，且只在同帧合并了两次以上时输出。
7. 同步 `Gameplay_Flow_Logic.md`：运行期链路改为“逻辑变化 → Request 聚合 → LateUpdate Flush → Presenter delta”。

## 验收

1. Playing 静止 10 秒：没有 `RequestRuntimeViewRefresh`，没有 Presenter 调用。
2. 非 Playing 静止 10 秒：没有持续 Request / Presenter 调用。
3. 单次命中：同一渲染帧最多一次 Presenter 调用；Board relocate 使用攻击前快照与最终 State。
4. 多个 FixedUpdate 落在同一渲染帧：只 Flush 一次，Slots / Stage 仍由既有 hash / version 正确消费最终状态。
5. 强制 Effects、命中、子弹结束：各自只触发一次 `RefreshEffectsAfterLayout`，不会下一 Tick 自动重新置脏。
6. Temp 复活、迁移、压缩、关闭：仍通过现有 Slots hash / Stage dirty 在下一次 Flush 同步。
7. Reveal、锤子、魔棒：原 Tween 和即时表现时机不变；没有因为合并刷新出现一帧延迟的输入或布局错误。
8. 执行 `git diff --check`；Unity 仅做定向编译与上述场景验证，不跑完整构建。
