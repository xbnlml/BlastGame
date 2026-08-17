# GamePassModule 模块代码导航

- 模块目录：`Assets/GameModule/GamePassModule/`

## 模块定位

- 通行证（Chefs Pass）赛季、星星、免费/付费奖励。
- 专题真源：[Game_Pass_Logic.md](../Game_Pass_Logic.md)

## 快速定位（关键词 → 类/方法）

| 关键词 / 问题 | 类 | 方法 / 关注点 | 路径 |
|---|---|---|---|
| 通行证 / Pass / 赛季 | `GamePassModel` | 活动状态与赛季重置 | `Script/Model/GamePassModel.cs` |
| Chefs Pass 头像框解锁 | `GamePassModel` | `HasUnlockFrame` | 同上 |
| 过关加星 / 星星进度 | `GamePassModel` | `TryAddWinStars` | 同上 |
| 免费奖励领取 | `GamePassModel` | `TryClaimFreeReward` | 同上 |
| 付费奖励领取 | `GamePassModel` | `TryClaimPaidReward` | 同上 |
| 循环奖励 / Node=9999 | `GamePassModel` | `TryClaimNextCyclicPaidReward` | 同上 |
| 通行证主界面 | `UIPassView` | 主界面入口 | `Script/UI/UIPassView.cs` |
| 通行证购买弹板 | `UIPassBuyView` | 购买入口 | `Script/UI/UIPassBuyView.cs` |
| 大厅通行证星星条 | `UIHomeLevelPassStarItem` | 大厅展示条目 | `Script/UI/UIHomeLevelPassStarItem.cs` |

## 入口类（简注）

| 类名 | 适用场景（简注） | 路径 |
|---|---|---|
| `GamePassModel` | 通行证活动状态模型 | `Assets/GameModule/GamePassModule/Script/Model/GamePassModel.cs` |
| `UIPassView` | 通行证主界面入口 | `Assets/GameModule/GamePassModule/Script/UI/UIPassView.cs` |
| `UIPassBuyView` | 通行证购买弹板入口 | `Assets/GameModule/GamePassModule/Script/UI/UIPassBuyView.cs` |

## Model 类

| 类名 | 路径 |
|---|---|
| `GamePassModel` | `Assets/GameModule/GamePassModule/Script/Model/GamePassModel.cs` |

## UI*View 类

| 类名 | 路径 |
|---|---|
| `UIPassBuyView` | `Assets/GameModule/GamePassModule/Script/UI/UIPassBuyView.cs` |
| `UIPassView` | `Assets/GameModule/GamePassModule/Script/UI/UIPassView.cs` |

## 其他核心类（可选）

| 类名 | 路径 |
|---|---|
| `UIHomeLevelPassStarItem` | `Assets/GameModule/GamePassModule/Script/UI/UIHomeLevelPassStarItem.cs` |
| `UIPassBuyViewBinder` | `Assets/GameModule/GamePassModule/Script/UI/ViewBinder/UIPassBuyViewBinder.cs` |
| `UIPassItem` | `Assets/GameModule/GamePassModule/Script/UI/UIPassItem.cs` |
| `UIPassViewBinder` | `Assets/GameModule/GamePassModule/Script/UI/ViewBinder/UIPassViewBinder.cs` |

## 返回主入口

- [GameModule 多 Agent 代码导航总纲](../gamemain-class-function-index.md)
