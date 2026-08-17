# Daily Delivery 玩法逻辑

## 摘要

- 模块：`DailyDeliveryModel`（`Assets/GameModule/DailyDeliveryModule/Script/Model/DailyDeliveryModel.cs`）。
- 目标：实现“14天循环签到”运行时逻辑：每日签到奖励 + 签到次数大节点奖励（`Fortnight_Tag*`）。
- 触发：登录/回主界面的弹窗队列（PopUpManager）仅在**当天日签未领**时弹出 `UIDailyDeliveryView`。队列判定前不领取当天；打开界面后自动签当天并播页内演出，随后自动领半月节点。
- View：`UIDailyDeliveryView`（`Assets/GameModule/DailyDeliveryModule/Script/UI/UIDailyDeliveryView.cs`）——14 天签到列表 + 3 个里程碑宝箱 + 进度条 + 倒计时；点击 Info 打开 `UIDailyDeliveryGuideView`。
- Item：`DailyDeliveryRewardItem`（小节点）/ `DailyDeliveryBigNodeRewardItem`（第 7/14 日）/ `FortnightNodeRewardItem`（半月宝箱，点击预览）。
- 新手签到：`GrandOpeningWeekModel`（`Assets/GameModule/GrandOpeningWeekModule/Script/Model/GrandOpeningWeekModel.cs`），见下文「Grand Opening Week」。

## 配置与数据

- 配置类：`Module.Daily_Delivery.Config.Daily_Delivery`
  - `Time_Anchor` / `Time_Duration`：活动窗口。
  - `Time_Duration`：玩家个人签到周期时长；周期结束时间按玩家解锁时间计算并归一到业务日 0 点。
  - `Daily_Reward1_14`：14 天每日奖励分组串。
  - `Fortnight_Tag1/2/3` + `Fortnight_Reward1/2/3`：大节点阈值与奖励。
- Profile：`ProfileDailyDelivery`
  - `NewEndTime`：当前玩家个人签到周期结束时间。
  - `RewardState`：日签领奖状态字典（`day(1..14)`）。
  - `BigNodeRewardState`：大节点领奖状态字典（key=requiredSignCount）。
  - `TaskId`：绑定当前玩家周期使用的赛季配置 ID。
  - `UnLockTime`：玩家首次解锁每日签到的原始时间戳，只写入一次。

## 时间与赛季口径

- `ResolveTimeData` 与 `GrandOpeningWeekModel` 保持一致：
  - 优先当前时间命中的配置窗口；
  - 若无命中，回退 `Time_Anchor` 最大的一条。
- 玩家内循环：首次解锁时以 `UnLockTime + Time_Duration` 计算 `NewEndTime`，并按业务日 0 点归一；后续周期从上次 `NewEndTime` 继续计算。
- 活动内循环日计算统一使用 `TimerManager.ResolveDayIndex`（统一偏移口径 `GameConst.DailyResetOffsetSeconds`），避免业务侧重复实现 dayIndex 公式。
- 每次登录、回主界面、跨天、打开界面或领取前都会检查 `NewEndTime`；检测到过期后按 `Time_Anchor` 选择当前时间之前最近的配置，重置奖励状态并刷新 `NewEndTime`。

## 自动领奖与补签

- 登录弹窗：`TryAutoClaimOnEntry(true)` / `HasUnclaimedCurrentDayReward()`
  - 仅当天日签未领才打开 `UIDailyDeliveryView`；当天没有可领日签时登录不弹窗。
  - 不在队列判定前调用 `TryClaimCurrentDayReward`。
- 打开界面后：
  1. 当天未领，间隔 `GameConst.DailyDeliveryAutoSignIdleSeconds` 后领取当天；
  2. 页内 `E_DD_trail01` 飞向进度条后涨水；
  3. 再 `TryClaimMonTagReward()` 自动领半月节点。
- 当天日签不可手点领取；补签仍走 `TryPatchSignByAd(int day)`（广告/券）。
- 日签格对齐新手签到四态：`DailyDeliveryRewardItem` 用 `ClaimedLockImg` / `Root/E_DD_Reward_Tx01` / `RetioBtn`。Day7/14 `DailyDeliveryBigNodeRewardItem` 待领粒子是 `Root/E_DD_Reward_Tx02`。`UIDailyDeliveryView` 调 `SetRewardTx01Active` / `SetRewardTx02Active`：当天未领才开，已领立刻关。补签不要用 `ResigningBtn`。已领必须关掉格子根上的 `UIButton`，否则点击仍播回弹。**易错**：粒子路径必须带 `Root/`；不要把 `BuLingBuLingBg` 当待领粒子；已领回弹不是 `ClaimedLockImg` 没开，是根按钮还在。
- 半月宝箱点击展开 `CommonRewardView`（`RewardTitleType.DailyDelivery`）预览内容，不通过点击领取。
- 红点：当天未签或半月节点可领（`HasPendingEntryReward`）。
- 大厅入口：`UIHomeLevelActivityItem` 间隔播放待机 / 展示。

## 触发接入点

- 登录后/回主界面：由 `PopUpManager` 队列统一调用 `OnTryShowEntryPopup`。
- 跨天：`DailyDeliveryModel.AddActivityEvent()` 订阅 `BlastMessageType.OnDayRefresh`，仅重评状态，不主动弹窗、不后台领取当天。

## Grand Opening Week

- 模块：`GrandOpeningWeekModel` / `UIGrandOpeningWeekView`。
- 登录弹窗：仅当天日签未领时打开界面；`IsOuterNewbieGuideComplete()` 先留接口，默认 `true`。第一次弹出等级门禁用 `ActivityConfig.Show_Condition`。
- 打开后当天未领先停 `GameConst.GrandOpeningWeekAutoSignIdleSeconds`（3 秒）再自动签当天，页内 `E_JDT_trail01` 飞进度，不弹全屏领奖。不可手点领当天。
- 补签：`TryPatchSignByAd(int day)`，必须按点击的 day 补。日签格 `GrandOpeningWeekSignRewardItem`：已领显示 `ClaimedLockImg`，待补签显示 `RetioBtn`（点击走广告/券补签）。`E_Reward_Tx01` 由 `UIGrandOpeningWeekView` 调用 `GrandOpeningWeekSignRewardItem.SetRewardTx01Active` 开关：该格是当天且 `RewardState[day]` 未领才开，已领或不是当天都关。领取成功后立刻调用关掉，不能等飞粒子结束。**易错**：粒子路径是 `Root/E_Reward_Tx01`；`Find("E_Reward_Tx01")` 会空引用并中断 `RefreshDailyList`，7 个特效保持默认全开。字段 `E_Reward_Tx01` 绑的是 `BuLingBuLingBg`，不是粒子。Day7 大格用 `Root/E_Reward_Tx02`，当天未领才开。
- Day7 是第 7 天日签大格，读 `RewardList` 第 7 段；1 个奖开 `Rwd`，≥2 个开 `DoubleRwd`。禁止用 `Endpoint_Reward` 填 Day7。
- `Endpoint_Reward` 只给最终大奖：活动中手点 `ClaimGroup/CommonGreenBtn` 走 `TryClaimEndpointReward`（读 `id:count` 或带括号数组），入口结束后补领弹 `CommonRewardView`。
- 入口结束后：7 天已齐且终点未领则自动补领，并标记下次登录/回主页弹 `CommonRewardView`（`RewardTitleType.GrandOpeningWeek`）。`CheckModelIsOpen` 在待展示补领弹板时仍为 true。
- 红点：当日未签或最终奖励未领。不做「领奖截止 14 天」。
- 倒计时：`NewUserEndTime` 是第一次登录当天时间戳（已有值不覆盖）。结束时间 = `NewUserEndTime + Time_Duration`。当天为第 1 天，打开后只签 Day1。主界面/大厅显示该剩余时间。大厅入口开关仍走配置 `Time_Anchor` 窗，禁止用个人结束时间关入口。
- 进度条：`BigRwdProgRoot` 下 `P1`–`P7` 对应 Day1–Day7。`Pn` 亮当且仅当第 n 天已领。只领 Day1 只亮 `P1`。每个 `Pn` 下的 `Effect` 只在该天领取当次打开（一次性动效），常驻刷新关掉。不要把 `Effect` 当已领常驻光。

## 当前非目标

- 14 天「领奖截止后额外缓冲期」策略扩展。
- 音效与打点。
- 外围新手引导完成条件的真实判定（接口默认 true）。

UI refresh convention: days 7 and 14 use `DailyDeliveryBigNodeRewardItem`; other days use `DailyDeliveryRewardItem`. Refreshing maps the `RewardListRoot` children in order to Day1-Day14, displays only valid nodes, and the activity countdown uses the same `UtilsTimeString.TimeString2` formatting and `Ended` terminal text as the beginner sign-in view.

Unlock timestamp: `DailyDeliveryModel.SetUnlockTime()` writes `ProfileDailyDelivery.UnLockTime` once. Player-cycle initialization calls it and persists `UnLockTime`, `TaskId`, and `NewEndTime` together.

Time normalization: use `TimerManager.ResolveDayStartTime(timestamp)` to convert a timestamp to the start of its business day. It shares the same `GameConst.DailyResetOffsetSeconds` convention as `ResolveDayIndex`.
