# GrandOpeningWeekModule 模块代码导航

- 模块目录：`Assets/GameModule/GrandOpeningWeekModule/`

- UI 约定：Day1-Day6 普通签到格；Day7 `GrandOpeningWeekSignBigRewardItem` 读 `RewardList` 第 7 段。终点大奖在 `Root/Middle/ClaimGroup`，手点 `CommonGreenBtn` 走 `TryClaimEndpointReward`（读 `Endpoint_Reward`），结束后补领弹 `CommonRewardView`。

## 模块定位

- 新手 7 天签到（Grand Opening Week）。
- 专题真源：[Daily_Delivery_Logic.md](../Daily_Delivery_Logic.md)（GrandOpeningWeek 部分）
- 勿与 14 天 Daily Delivery 混淆：见 [daily-delivery-module.md](daily-delivery-module.md)

## 快速定位（关键词 → 类/方法）

| 关键词 / 问题 | 类 | 方法 / 关注点 | 路径 |
|---|---|---|---|
| 新手签到 / 7天签到 / Grand Opening | `GrandOpeningWeekModel` | 活动状态与领奖 | `Script/Model/GrandOpeningWeekModel.cs` |
| 自动领奖 / 回主界面弹新手签到 | `GrandOpeningWeekModel` | `TryAutoClaimOnEntry` / `HasUnclaimedCurrentDayReward` | 同上 |
| 当日领奖 | `GrandOpeningWeekModel` | `TryClaimCurrentDayReward`（打开后先停 3 秒再领） | 同上 |
| 广告补签 | `GrandOpeningWeekModel` | `TryPatchSignByAd(int day)` | 同上 |
| 终点大奖 / 最终奖励 | `GrandOpeningWeekModel` | `TryClaimEndpointReward`；结束后自动补领弹 `CommonRewardView` | 同上 |
| 外围引导门禁 | `GrandOpeningWeekModel` | `IsOuterNewbieGuideComplete`（默认 true） | 同上 |
| 新手签到主界面 / LoopGridView | `UIGrandOpeningWeekView` | day=`index+1` 映射 | `Script/UI/UIGrandOpeningWeekView.cs` |
| 签到格子 | `GrandOpeningWeekSignRewardItem` | 已领 `ClaimedLockImg` / 待领 `E_Reward_Tx01` / 补签 `RetioBtn` | `Script/UI/GrandOpeningWeekSignRewardItem.cs` |
| 终点进度点 | `BigRewardStateItem` | filled / empty | `Script/UI/BigRewardStateItem.cs` |

## 入口类（简注）

| 类名 | 适用场景（简注） | 路径 |
|---|---|---|
| `GrandOpeningWeekModel` | 七日签到活动状态模型；红点刷新在 `BindProfileDataReference` 后执行，领奖状态读取经 `TryEnsureProfileData` 兜底 | `Assets/GameModule/GrandOpeningWeekModule/Script/Model/GrandOpeningWeekModel.cs` |
| `UIGrandOpeningWeekView` | 七日签到活动主界面入口（LoopGridView 使用 `index+1` 映射 day，避免 row 维度导致 day 重复） | `Assets/GameModule/GrandOpeningWeekModule/Script/UI/UIGrandOpeningWeekView.cs` |
| `GrandOpeningWeekSignRewardItem` | 每日签到格子渲染 | `Assets/GameModule/GrandOpeningWeekModule/Script/UI/GrandOpeningWeekSignRewardItem.cs` |

## Model 类

| 类名 | 路径 |
|---|---|
| `GrandOpeningWeekModel` | `Assets/GameModule/GrandOpeningWeekModule/Script/Model/GrandOpeningWeekModel.cs` |

## UI*View 类

| 类名 | 路径 |
|---|---|
| `UIGrandOpeningWeekView` | `Assets/GameModule/GrandOpeningWeekModule/Script/UI/UIGrandOpeningWeekView.cs` |

## 其他核心类（可选）

| 类名 | 路径 |
|---|---|
| `BigRewardStateItem` | `Assets/GameModule/GrandOpeningWeekModule/Script/UI/BigRewardStateItem.cs` |
| `GrandOpeningWeekSignRewardItem` | `Assets/GameModule/GrandOpeningWeekModule/Script/UI/GrandOpeningWeekSignRewardItem.cs` |
| `UIGrandOpeningWeekViewBinder` | `Assets/GameModule/GrandOpeningWeekModule/Script/UI/ViewBinder/UIGrandOpeningWeekViewBinder.cs` |

## 返回主入口

- [GameModule 多 Agent 代码导航总纲](../gamemain-class-function-index.md)
