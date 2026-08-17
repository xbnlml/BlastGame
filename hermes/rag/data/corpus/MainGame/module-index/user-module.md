# UserModule 模块代码导航

- 模块目录：`Assets/GameModule/UserModule/`
- 专题真源：[Player_Data_Logic.md](../Player_Data_Logic.md)
- Playbook：`Playbooks/player-data.md`

## 模块定位

- 玩家核心数据与运行时管理（体力/金币/等级/道具/Profile 同步）。

## 快速定位（关键词 → 类/方法）

| 关键词 / 问题 | 类 | 方法 / 关注点 | 路径 |
|---|---|---|---|
| 首登 / 初始化 / Profile 接入 | `UserModuleManager` | `InitializeFromProfile` | `Script/Runtime/UserModuleManager.cs` |
| 默认档判定 / 首登填充 | `UserMainData` | `IsDefaultProfile` / `ApplyInitialData` / `MarkInitialDataSynced` | `Script/Core/UserMainData.cs` |
| 进关体力门槛 | `UserModuleManager` / `UIHomeLevelView` / `BlastLevelEntry` | `HasEnoughHealthForLevelEntry`；大厅进关与失败重试不足时打开 `UIHealthView` | `Script/Runtime/UserModuleManager.cs` |
| 扣体 / 失败扣体 | `UserModuleManager` | `TrySpendHealthAndSync` | `Script/Runtime/UserModuleManager.cs` |
| 时间回体 | `UserMainData` | `TryRecoverHealthByTime` | `Script/Core/UserMainData.cs` |
| 无限体力 | `UserMainData` / `UserModuleManager` | `IsEndlessHealthActive` / `ExtendEndlessHealth`；`ExtendEndlessHealthAndSync`；`EndlessHealthChanged` / `SyncEndlessHealthActiveState` | Core / Runtime |
| 补体 / 广告补体 | `UserModuleManager` | `TryAddHealthAndSync` / `GetHealthViewSnapshot` | `Script/Runtime/UserModuleManager.cs` |
| 广告券 | `UserModuleManager` | `TryConsumeRemoveAdCountAndSync` | `Script/Runtime/UserModuleManager.cs` |
| 金币 / 扣金币 / 花金币 / SpendCoin | `UserModuleManager` | `AddCoinAndSync` / `ClearCoinAndSync` / `TrySpendCoinAndSync`；`UserMainData.AddCoin` / `UseCoin` | Runtime / Core |
| 等级 / 通关结算 | `UserModuleManager` | `SetLevelAndSync` / `SetLevelDataAsync` | `Script/Runtime/UserModuleManager.cs` |
| 道具库存 | `UserModuleManager` | `GetPowerUpCount` / `AddPowerUpAndSync` / `TrySpendPowerUpAndSync` | `Script/Runtime/UserModuleManager.cs` |
| 持久化 / 上传标记 | `UserModuleManager` | `PersistProfile` / `PersistCurrentData` | `Script/Runtime/UserModuleManager.cs` |
| 付费分层 / RealPaidTotal | `UserModuleManager` | `GetRealPaidTotalCents` / `GetPaidPurchaseLayer` / `GetPaidLayerId` | `Script/Runtime/UserModuleManager.cs` |
| Top 栏体力 HUD | `TopUIView` / `LifeNumItem` | `RefreshHealthDisplay` → `PanelTopbar`；无尽时 `lifeTimeTxt` 倒计时；监听 `HealthChanged`/`EndlessHealthChanged`；点击 → `UIHealthView` | `HomeModule/.../TopUIView.cs` |
| 体力弹板 | `UIHealthView` | 无尽 `EndLess`/`EndLessTimeText`；非无尽 `HealthText` + `MaxHealthText`/`HealthTimeText` | `HomeModule/.../UIHealthView.cs` |
| 用券确认 | `RemoveAdView` | `RemoveAdViewOpenArgs` | `HomeModule/.../RemoveAdView.cs` |

规则细则见专题文档，本表只做定位。

## 入口类

| 类名 | 适用场景 | 路径 |
|---|---|---|
| `UserModuleManager` | 运行时入口（体力/金币/等级/道具/持久化） | `Assets/GameModule/UserModule/Script/Runtime/UserModuleManager.cs` |
| `UserMainData` | Profile 承接与纯数据规则 | `Assets/GameModule/UserModule/Script/Core/UserMainData.cs` |

## UI*View

- 体力 HUD 在 HomeModule：`TopUIView` / `UIHealthView` / `RemoveAdView`（规则见专题「体力 HUD」）。

## 返回主入口

- [GameModule 多 Agent 代码导航总纲](../gamemain-class-function-index.md)
