# DailyDeliveryModule 模块代码导航

- 模块目录：`Assets/GameModule/DailyDeliveryModule/`

## 模块定位

- 14 天循环每日签到（Daily Delivery）。
- 专题真源：[Daily_Delivery_Logic.md](../Daily_Delivery_Logic.md)
- 勿与新手 7 天签到混淆：新手见 [grand-opening-week-module.md](grand-opening-week-module.md)

## 快速定位（关键词 → 类/方法）

| 关键词 / 问题 | 类 | 方法 / 关注点 | 路径 |
|---|---|---|---|
| 14天签到 / 每日签到 / Daily Delivery | `DailyDeliveryModel` | 活动状态与领奖 | `Script/Model/DailyDeliveryModel.cs` |
| 自动领奖 / 回主界面弹签到 | `DailyDeliveryModel` | `TryAutoClaimOnEntry` / `HasUnclaimedCurrentDayReward` | 同上 |
| 当日签到领奖 | `DailyDeliveryModel` | `TryClaimCurrentDayReward`（打开界面后自动签） | 同上 |
| 里程碑宝箱 / 5/8/14 大节点 | `DailyDeliveryModel` | `TryClaimMonTagReward` / `TryClaimSingleMonTag` | 同上 |
| 广告补签 | `DailyDeliveryModel` | `TryPatchSignByAd` | 同上 |
| 签到主界面 / LoopListView2 | `UIDailyDeliveryView` | 14 天列表 + 进度条 | `Script/UI/UIDailyDeliveryView.cs` |
| 每日签到说明 / Info | `UIDailyDeliveryGuideView` / `UIDailyDeliveryGuideViewBinder` | appear/idle 动画与说明节点绑定 | `Script/UI/UIDailyDeliveryGuideView.cs` / `Script/UI/ViewBinder/UIDailyDeliveryGuideViewBinder.cs` |
| 日签格子 | `DailyDeliveryRewardItem` | Locked/Claimable/Claimed/Resignable | `Script/UI/DailyDeliveryRewardItem.cs` |
| 半月宝箱预览 | `FortnightNodeRewardItem` | 点击打开 `CommonRewardView` | `Script/UI/FortnightNodeRewardItem.cs` |

## 入口类（简注）

| 类名 | 适用场景（简注） | 路径 |
|---|---|---|
| `DailyDeliveryModel` | 14 天签到活动数据模型与领奖状态判断（含红点刷新） | `Assets/GameModule/DailyDeliveryModule/Script/Model/DailyDeliveryModel.cs` |
| `UIDailyDeliveryView` | 14 天签到活动主界面入口 | `Assets/GameModule/DailyDeliveryModule/Script/UI/UIDailyDeliveryView.cs` |
| `FortnightNodeRewardItem` | 签到节点奖励条目渲染 | `Assets/GameModule/DailyDeliveryModule/Script/UI/FortnightNodeRewardItem.cs` |

## Model 类

| 类名 | 路径 |
|---|---|
| `DailyDeliveryModel` | `Assets/GameModule/DailyDeliveryModule/Script/Model/DailyDeliveryModel.cs` |

## UI*View 类

| 类名 | 路径 |
|---|---|
| `UIDailyDeliveryView` | `Assets/GameModule/DailyDeliveryModule/Script/UI/UIDailyDeliveryView.cs` |

## 其他核心类（可选）

| 类名 | 路径 |
|---|---|
| `DailyDeliveryRewardItem` | `Assets/GameModule/DailyDeliveryModule/Script/UI/DailyDeliveryRewardItem.cs` |
| `FortnightNodeRewardItem` | `Assets/GameModule/DailyDeliveryModule/Script/UI/FortnightNodeRewardItem.cs` |
| `UIDailyDeliveryViewBinder` | `Assets/GameModule/DailyDeliveryModule/Script/UI/ViewBinder/UIDailyDeliveryViewBinder.cs` |

## 返回主入口

- [GameModule 多 Agent 代码导航总纲](../gamemain-class-function-index.md)
