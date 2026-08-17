# HomeModule 模块代码导航

专题文档： [BottomUIView 重构](../BottomUIView_Refactor.md)

- 模块目录：`Assets/GameModule/HomeModule/`

## 模块定位

- 大厅与首页展示模块。
- 体力规则真源：[Player_Data_Logic.md](../Player_Data_Logic.md)；类索引也见 [user-module.md](user-module.md)。

## 个人资料头像选择状态

- `UserProfileModel` 同时维护头像的已保存状态与当前预览状态：`IsSaved` 对应玩家当前实际使用的头像，`IsSelected` 对应个人资料界面当前预览选中的头像。
- `AvatarChooseItem` 的 `Yes` 只展示已保存头像，`SelectImg` 只展示当前预览头像；两种状态可以独立存在。
- `UIProfileView` 点击头像后仅刷新点击前后的两个头像项，不刷新整个 `AvatarGridView`，避免其他头像按钮触发共同的按压动画。

## 快速定位（关键词 → 类/方法）

| 关键词 / 问题 | 类 | 方法 / 关注点 | 路径 |
|---|---|---|---|
| 大厅 / 主界面 / 开始关卡 | `UIHomeLevelView` | 大厅入口、活动倒计时；按用户分组关卡 `DifficultyLevel` 显隐 `PlayLvObjs`/`Bgs`（`ResolveSeriesRelativeFolderPath`）；体力不足打开 `UIHealthView` | `Script/UI/UIHomeLevelView.cs` |
| Top 栏 / 顶栏体力 HUD | `TopUIView` / `LifeNumItem` | `LifeNumItem` 监听 `HealthChanged`/`EndlessHealthChanged`；无尽显示倒计时；点击打开 `UIHealthView` | `Script/UI/TopUIView.cs` |
| 体力弹板 / 补体 UI | `UIHealthView` | 无尽：`EndLess`+`EndLessTimeText`；非无尽：`HealthText` 数量，满体 `MaxHealthText` / 未满 `HealthTimeText`；广告补体 | `Script/UI/UIHealthView.cs` |
| Top 栏金币展示 | `TopUIView` / `CoinNumItem` | `RefreshCoinText` → `PanelTopbar.TryGetCoinItem`；飞币 `BeginCoinFlyPresentation` / `ApplyCoinFlyDelta`；配置 `GamePanelConfig.TopUIView` | `Script/UI/TopUIView.cs` |
| 广告券确认弹板 | `RemoveAdView` | `RemoveAdViewOpenArgs`；关闭按钮也会回调 `OnFinished` | `Script/UI/RemoveAdView.cs` |
| 个人资料 / 头像 / 头像框 / 昵称 / 改名 | `UIProfileView` / `UIChangeUserNameView` / `UserProfileModel` | 头像保存派发 `OnProfileAvatarChanged`；改名确认后派发 `OnProfileUserNameChanged`，`UIProfileView` 订阅后刷新头部昵称 | `Script/UI/` |
| 设置 / 音效 / 震动 / 铃声 | `UISettingsView` | 开关读写 `Profile.SettingData`（`MusicSwitch`/`SoundSwitch`/`HapticSwitch`）；音效经 `IAudioSystem`；**震动开关**经 `GameHapticManager.SetHapticsEnabled`（见 [Nice_Vibrations_Haptic_Logic.md](../Nice_Vibrations_Haptic_Logic.md)）；**通知/铃声开关**：显示状态读取 `ServiceNotifications.IsNotificationOn()`，点击 `OnClickRingBtn` 调用 `ServiceNotifications.TryOpenNofications()`；点击后 `RefreshSwitchState()` 立即刷新；`DeleteBtn`→删除账号；`SaveProgressBtn`→平台登录存档 | `Script/UI/UISettingsView.cs` |
| 存档登录 / 平台绑定 | `UISaveProgressView` | FB/Google/Apple `PassportHub.Bind*` / `UnBind*`；成功/失败弹板 | `Script/UI/UISaveProgressView.cs` |
| 删除账号 | `UIDeleteAccountInfoView` / `UIDeleteAccountConfirmView` | Info→Confirm（输入 `DELETE`，大小写不敏感）；Warning 关闭 | `Script/UI` |
| 底栏 | `BottomUIView` | 底栏入口 | `Script/UI/BottomUIView.cs` |

## 入口类（简注）

| 类名 | 适用场景（简注） | 路径 |
|---|---|---|
| `UIHomeLevelView` | 大厅主界面入口；活动倒计时每秒立即刷新并使用 `UtilsTimeString.TimeString2` 格式；`PlayLvObjs`/`Bgs` 按用户分组关卡 `DifficultyLevel`(0/1/2) 只显对应难度根节点（路径经 `BlastLevelLoader.ResolveSeriesRelativeFolderPath`），其下 `LvTexts` 文案 `Level {n}`；进关体力不足→`UIHealthView` | `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelView.cs` |
| `TopUIView` | 顶栏入口（体力/货币/活动）；体力倒计时刷新间隔同 `refreshIntervalSeconds` | `Assets/GameModule/HomeModule/Script/UI/TopUIView.cs` |
| `UIHealthView` | 体力详情弹板入口 | `Assets/GameModule/HomeModule/Script/UI/UIHealthView.cs` |
| `UserProfileModel` | 个人资料展示模型（头像/头像框状态与选择后红点刷新） | `Assets/GameModule/HomeModule/Script/UI/UserProfileModel.cs` |

## Model 类

| 类名 | 路径 |
|---|---|
| `UserProfileModel` | `Assets/GameModule/HomeModule/Script/UI/UserProfileModel.cs` |

## UI*View 类

| 类名 | 路径 |
|---|---|
| `UIHealthView` | `Assets/GameModule/HomeModule/Script/UI/UIHealthView.cs` |
| `UIHomeLevelView` | `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelView.cs` |
| `UIProfileView` | `Assets/GameModule/HomeModule/Script/UI/UIProfileView.cs` |
| `UIChangeUserNameView` | `Assets/GameModule/HomeModule/Script/UI/UIChangeUserNameView.cs` |
| `UISettingsView` | `Assets/GameModule/HomeModule/Script/UI/UISettingsView.cs` |
| `UISaveProgressView` | `Assets/GameModule/HomeModule/Script/UI/UISaveProgressView.cs` |
| `SettingModel` | `Assets/GameModule/HomeModule/Script/Model/SettingModel.cs` |
| `UIDeleteAccountInfoView` | `Assets/GameModule/HomeModule/Script/UI/UIDeleteAccountInfoView.cs` |
| `UIDeleteAccountConfirmView` | `Assets/GameModule/HomeModule/Script/UI/UIDeleteAccountConfirmView.cs` |
| `UISignInSuccessView` | `Assets/GameModule/HomeModule/Script/UI/UISignInSuccessView.cs` |
| `UISignInFailView` | `Assets/GameModule/HomeModule/Script/UI/UISignInFailView.cs` |

## 其他核心类（可选）

| 类名 | 路径 |
|---|---|
| `BlastAudioSettings` | `Assets/GameModule/HomeModule/Script/Core/BlastAudioSettings.cs` |
| `BottomUIView` | `Assets/GameModule/HomeModule/Script/UI/BottomUIView.cs` |
| `BottomUIViewBinder` | `Assets/GameModule/HomeModule/Script/UI/ViewBinder/BottomUIViewBinder.cs` |
| `LevelActivityData` | `Assets/GameModule/HomeModule/Script/RunTime/LevelActivityData.cs` |
| `RemoveAdView` | `Assets/GameModule/HomeModule/Script/UI/RemoveAdView.cs` |
| `RemoveAdViewOpenArgs` | `Assets/GameModule/HomeModule/Script/UI/RemoveAdView.cs` |
| `TopUIView` | `Assets/GameModule/HomeModule/Script/UI/TopUIView.cs` |
| `TopUIViewBinder` | `Assets/GameModule/HomeModule/Script/UI/ViewBinder/TopUIViewBinder.cs` |
| `UIHealthViewBinder` | `Assets/GameModule/HomeModule/Script/UI/ViewBinder/UIHealthViewBinder.cs` |
| `UIHomeLevelActivityItem` | `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelActivityItem.cs` |

## Profile 头像与头像框展示

- `UserProfileModel` 的 Avatar/Frame 条目同时携带静态/动态标记；头像框条目还携带限时标记与配置表 `Unlock_Info`，供 `UIProfileView` 刷新展示和锁定提示。
- `AvatarItem` 与 `FrameItem` 负责单独的图片、静态/动态状态、限时标记和锁定标记展示；`UserAvatarItem` 组合头像与头像框，复用于主页 Top 和 Profile 顶部预览。
- `AvatarChooseItem` 与 `FrameChooseItem` 负责列表单元格状态和点击回调。循环列表刷新时只更新当前回调，按钮监听在组件生命周期内绑定一次，避免复用后重复触发。
- `UIProfileView` 点击已解锁头像框时更新预览；点击未解锁头像框时使用条目的 `Unlock_Info` 显示解锁提示。Chefs Pass 头像框的解锁状态由 `GamePassModel.HasUnlockFrame` 查询。

## 平台存档登录失败提示

- `UISaveProgressView` 将 Facebook、Google、Apple 的平台名和失败原因传入 `UISignInFailView`。
- `UISignInFailView.OnOpen` 接收平台参数，使用 `UIStateToggle` 切换对应平台图标，并刷新失败文案；默认平台为 Facebook。
- `UISignInFailView` 的 `Try Again` 按 `_failedPlatform` 重新发起对应平台绑定；成功打开成功提示，失败或取消重新打开失败提示，关闭按钮仍只关闭窗口。
- `UISignInSuccessView` 接收成功登录的平台参数，按平台切换 `IconSwitch`，并让 `TipText` 显示 `Signed in with` 和平台名称。

## 返回主入口

- [GameModule 多 Agent 代码导航总纲](../gamemain-class-function-index.md)
