# 道具系统说明（Unity）


## 类职责清单

### Runtime（业务编排）

- `BlastGameController.PowerUps`：道具统一门面，负责校验、消耗、状态修改与刷新触发。
- `BlastPowerUpWand` / `BlastPowerUpHammer` / `BlastFailReviveTempSlots`：各自承担算法逻辑，不由 UI 决策。
- `BlastWandShuffleAnim`：魔棒洗牌换位调度（直线、统一用时）；不改 Candidates。

### UI（入口与交互）

- `BlastPowerUpView`：只负责开道具弹板与入口分流，不直接扣费或改玩法状态。
- `UIGamePropBuyView`：局内道具金币购买弹板；`CommonBuyBtn` 扣币后 `PanelTopbar` `PlayAdd` 滚金币，滚完再 `Close` 并播 `close1_01~04`；到 `50/60s` 再 `AddPowerUpAndSync`（经 `PowerUpCountChanged` 刷道具栏），普通关闭播 `close2`。
- `UIGamePropUseViewBase` 与各子类：只处理预览、确认、关窗流程；确认后交 Runtime 执行。
- `BlastPropUseUiSession`：维护弹板会话态（开闭计数、界面抬升、切场清理）。
- `BlastPowerUpConfirm.RequestPowerUpPurchase`：打开 `UIGamePropBuyView`（解锁/回放仍走 `UINotice`；锁定 tip 走 `UIBubble`/`CommonUIManager`）。
- `BlastStageView.PlayWandShuffleMoves` / `CancelWandShuffleMoves`：魔棒换位表现与打断归位。
- `BlastPowerUpConfirm.RequestPowerUpPurchase`：打开 `UIGamePropBuyView`（解锁 tip / 回放道具提示 / 回放胜负 → `CommonPopToast`；锁定 tip → `UIBubble`）。

### Config/Core（配置与契约）

- `BlastDataConfig`：价格、解锁关卡、续命等配置真源。
- `BlastPowerUpType` / `BlastMessageType`：跨 UI/Runtime/数据层共用契约定义。
- 锤子新手引导为纯 UI 临时表演：假格子点击只清理锤子选择态，不触发真实 Board 刷新；假格子由 `BlastHammerGuideFakePerformance` 自行回收，盘面归位后调用 `ReleaseHeldEffectClose` 进入普通 close 动画。
- 道具 1–4 的免费引导弹板均隐藏 CloseUI；普通道具使用仍显示 CloseUI。
- 所有道具 UseView 效果完成后统一使用普通 `Close(false)` 播放 close 退场动画。

## 协作边界

- 道具流程固定为：资格校验 -> 消耗校验 -> 纯数据修改 -> Presenter 刷新 -> 记录 replay/BI。
- 魔棒洗牌：按完整 feature 实体置换（`color/secondColor/triangle/amount/secret/lock_`）；Single/Pair 分组洗，Pair 的两个 link 成员不可拆分，落点只保留目标格的 `x/y/cellIndex` 并重建 link 邻接关系。飞行中 source feature 的 SpecialMark/Lock 随实体移动，落定后不再按旧目标格覆盖。
- UI 不直接修改 `BlastGameState`，仅发起意图与承接反馈。
- Rollback/FailRevive 与主状态机协作，但恢复口径由 Runtime 定义，不由视图定义。

## 适用范围

说明道具从 UI 使用到 Runtime 执行、回滚和结算的主链路。具体按钮和动画不在本文维护。

## 1. 统一入口

```text
PowerUp UI
  → BlastPropUseUiSession
  → BlastGameController.PowerUps
  → validate / consume / mutate state
  → Presenter refresh
  → BI / replay / settlement when needed
```

- `BlastPropUseUiSession` 管理弹板打开、确认和关闭。
- `BlastGameController.PowerUps` 是玩法道具 facade。
- 道具不能直接修改 View 或绕过状态校验。

## 2. 道具职责

| 道具 | 当前主职责 | 入口 |
|---|---|---|
| Magnet / Wand | 选择并处理候选或目标 | `TryUseWand` / 对应选择流程 |
| Magnet 放置飞 | Put 后立刻攻击掩码 + FlyingIn=showDelay+Settings2；延迟后道具 2to3（`Prop Use UI/磁铁飞行`）；磁铁专用 2to3 可配置「飞行时间→缩放倍率」曲线与归一化 Spine 速度曲线，飞行结束仍严格匹配 `FixedDuration`，到达 Slot 后恢复起飞缩放；飞挂弹板 `MagnetFlyParent` 盖过遮罩，落地 Adopt 后关窗 | `TryApplyStageCellClick` 磁铁 / `ResolveStageAnimal2To3FlySettings(true)` / `UIGameProp1UseView` |
| Wand 洗牌 | 数据：Single/Pair **分组**完整 feature 置换 + 置换映射；表现：feature 随实体直线换位→换绑；离手前排闪切 idle1，新进前排普通 `1to2` / 神秘 `1to2_appear` + 描边 | `TryUseWand` / `BlastPowerUpWand` / `BlastWandShuffleAnim` / `PlayWandShuffleMoves` |
| Hammer | 点击立刻 show/停闪缩/扣费；延迟后 Closing+逐块 idle 飞（row 升序、同行左→右；块间间隔衰减默认 0.95；飞中终缩可配），飞完回收下落；被消普通块 `health` 总和按 ≤`stageCandidateNormalAmount`（默认 20）切组，整组随机插入候补队列同色 run 组缝（`seed=removed`，一次 Random 多次 Next），补回后再 Settle；**不扣** Stage/Slot；全程禁 Stage 点击 | `ToggleHammerMode` / `OnHammerBoardCellPicked` / `BlastPowerUpHammer` |
| Magic Box | 按规则处理候选/槽位 | `TryUseMagicBox` |
| Fail Revive | 失败后的临时槽与续命 | `UIGameContinueView` / `EvaluateContinueState` |
| Rollback | 恢复最近合法快照 | `BlastGameRollbackRuntime` |

### 2.1 魔棒换位落定顺序

1. 校验 / 扣费 / `apply` 洗牌：Single/Pair **分别** Fisher–Yates，搬运完整 feature；变化判定基于 apply 前后的 payload，保证 from→to 为置换（不跨 Kind 混洗）
2. 开 `_wandShuffleAnimActive` 门控；弹板 `HoldClose` 至换位落定后再关窗恢复攻击
3. 起跳：source 的 SpecialMark、Lock 与动物保持同一实体；离手前排闪切 `idle_1`+关描边；其余描边 0.2s 渐隐；link follow 使用 destination feature 对应的 incoming source，保证 pair 整体跟随
4. `PlayWandShuffleMoves`：旧视觉按映射直线飞到目标格点（统一 duration + ProgressEase）
5. 完成：起飞前验证 from/to 是完整置换且每个端点有 view；落定后 **换绑**，同时重建目标格的 displayRow 映射（失败则统一 Snap 旧格点并结束 follow）→ `NotifyCandidateContentChanged` → 内容刷新优先于推进动画（保持 source feature，抑制自动 idle2/描边闪现）→ 新进前排普通 `1to2` / 神秘 `1to2_appear` + 描边 / 其余前排描边渐显 → 解门控
6. 回放 `isApplyingAction`：跳过位移，直接落定刷新；seed/signature 口径不变
7. 卸载 / Rollback：中断时按旧绑定弹回格点再刷；避免半飞残留

### 2.2 Prop1/Prop2 行距与 BlastAreaRoot

- Prop1 磁铁 / Prop2 魔棒 appear、关闭：均 `SetMagnetMode(..., layoutDuration, ease)`，与 BlastAreaRoot 抬升/还原 **同时长** tween 第 4 行及以后（`stageHiddenRowsExtraGap`），禁止瞬移。入口：磁铁 `RunStagePowerUpRevealTransition`；魔棒 `EnterWandPreview` / `ExitWandPreview`（Raise/Restore 读 `propUseBlastAreaRootRaiseTween` / `RestoreTween`）。
- `SetPowerUpSelectionState` **不得**无 duration 调 `SetMagnetMode`（否则 Enter 前先 Snap，第 4/5 行闪切、后续 tween 空跑）。
- Presenter 的无动画刷新在 `_magnetLayoutTweenActive` 期间只同步状态，不写回终点；Sync 不打断行距位移。
- 磁铁列推进：已有 cell 走 `ApplyExistingTargetState`；运行期新 Acquire 的末行 cell 从 `displayRow+1` 画面外移入，时长 `ResolveStageAnimalFlyDurationOtherRowsAdvance()`（`stageAnimalOtherRowsAdvanceFlySettings`）。`BindInitialCandidates` 仍 Snap。
- 魔棒不与另一轮洗牌、落子推进或行距过渡重叠；回放路径可直接快进。

## 3. 统一执行边界

每个道具都必须经过：

1. 当前状态和使用条件校验；
2. 金币、库存或广告资格校验；
3. 纯数据状态修改；
4. Presenter 增量刷新；
5. 记录 replay / BI（若该动作属于可记录事件）。

失败时不应留下半消费、半修改或未清理的 UI 状态。

### 3.1 战斗暂停

- 实玩：`PropUseUi.IsOpen`（道具使用弹板打开）即 `skipAttackTargetCheck`，暂停主攻击。
- 关窗顺序：先落地道具效果（含 Hold 等到换位/吸收/回退重建完成）→ `UnregisterOpen` → 恢复攻击。
- 魔棒/回退与磁铁/锤子一样走 `HoldCloseUntilEffectReleased`：效果完成再 `ReleaseHeldEffectClose`。
- 弹板已关但 `_wandShuffleAnimActive` / `_hammerAbsorbEffectActive` 未结束时仍暂停。
- 暂停期间冻结连击窗（墙钟不计入 `shootIntervalMs`）。
- 回放无真实弹板：以 `IsHammerSelecting` / `IsMagnetSelecting` 对齐暂停窗口。
- 道具使用期间由道具状态门控战斗推进，不使用 `PauseCombatForPowerUpMs` 按时长暂停。

## 4. 回滚与续命

- Rollback 使用深拷贝快照，恢复后重新绑定 Board、Stage、Slots。
- 续命只恢复允许恢复的局内状态，不重新伪造已经结算的进度。
- 失败、续命和扣体由 `BlastGameController.State` 统一协调。

## 5. 代码入口

| 问题 | 入口 |
|---|---|
| 道具 UI 会话 | `BlastPropUseUiSession` |
| 道具统一 facade | `BlastGameController.PowerUps` |
| 锤子 | `ToggleHammerMode` / `OnHammerBoardCellPicked` / `PlayHammerAbsorbCloseVisual` / `BlastPowerUpHammer.RefundAmmoIntoQueue` |
| 锤子 UI 配置 | `BlastUIRuntimeConfig`：`ResolvePropShowEffectDelaySeconds` / `ResolveHammerAbsorbFlySettings(column, boardWidth)`（路径仅 PathCurve+ProgressEase，按列选 1–5；时长用 `hammerAbsorbFlyDurationSeconds`） / `ResolveHammerAbsorbTotalCollectDurationSeconds` / 终缩 `ResolveHammerAbsorbFlyEndScaleFactor`+`ResolveHammerAbsorbFlyEndScaleCurve` / `FillHammerAbsorbBlockTakeoffDelaysSeconds`（衰减默认 0.95） |
| 磁铁 2to3 飞配置 | `BlastUIRuntimeConfig` → `Prop Use UI` → `磁铁飞行`：`stageAnimal2To3FlySettings2` / `magnet2To3FlyScaleCurve`（t→缩放倍率） / `magnet2To3AnimSpeedCurve`（仅磁铁 Settings2；速度曲线平均归一化） |
| BlastAreaRoot 抬升/还原 | 开板抬升；点 Close / 效果关窗时与退场同时还原（勿等 OnHidden）；Prop1/Prop2 行列 tween 对齐同时长 | `propUseBlastAreaRootRaiseTween` / `RestoreTween` / `SetMagnetMode(duration,ease)` / `RunStagePowerUpRevealTransition` |
| 锤子逐块吸收飞 | `BlastHammerAbsorbBlockFly.ScheduleOrdered` / `PlayHammerAbsorbCloseVisual`（`UiRewardFlyTween.FlyWorld` + 终缩） |
| 法杖 | `TryUseWand` / `BeginWandShuffleVisual` |
| 法杖换位调度 | `BlastWandShuffleAnim` / `BlastStageView.PlayWandShuffleMoves` |
| 法杖换位 UI 配置 | `BlastUIRuntimeConfig`：`ResolveWandShuffleMoveDurationSeconds` / `ResolveWandShuffleMoveProgressEase` / `ResolveWandShuffleOutlineFadeSeconds`（直线路径，无 PathCurve） |
| 魔法盒 | `TryUseMagicBox` |
| 回滚 | `BlastGameRollbackRuntime.BuildSnapshot` |
| 失败续命 | `BlastGameController.State.EvaluateContinueState` |
