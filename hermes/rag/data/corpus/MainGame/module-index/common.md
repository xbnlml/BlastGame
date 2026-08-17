# Common 模块代码导航

- 模块目录：`Assets/GameModule/Common/`

## 模块定位

- 公共能力与基础设施模块。
- 重点承载全局计时、资源加载、弹板调度、模型注册、场景切换与回大厅流程。

## 入口类（简注）

| 类名 | 适用场景（简注） | 常用入口方法 | 路径 |
|---|---|---|---|
| `TimerManager` | 全局定时、延时、倒计时、跨天重置检测 | `AddListener` / `AddDelay` / `AddCountdown` / `StartDailyReset` / `CheckDayChangeImmediate` / `ResolveDayIndex` | `Assets/GameModule/Common/Script/TimerManager.cs` |
| `GameModelManager` | 活动模型注册、初始化、按活动类型路由入口 | `InitializeFromProfile` / `GetModelByActivityType` / `OpenActivityView` / `GetActivityConfig` / `DisposeAll` | `Assets/GameModule/Common/Script/Model/GameModelManager.cs` |
| `PopUpManager` | 按触发时机编排弹板队列与中断 | `TriggerPopups` / `Interrupt` | `Assets/GameModule/Common/Script/PopUpManager.cs` |
| `ResourcesManager` | 统一资源加载/卸载（含白名单常驻） | `LoadAsset` / `LoadAssetASync` / `Unload` / `LoadTexture` / `LoadSpriteAtlas` / `LoadSprite` | `Assets/GameModule/Common/Script/ResourcesManager.cs` |
| `SpriteAtlasLateBinding` | 真机 AB 下 SpriteAtlas 晚绑定（防图集 Sprite 全白） | `Register` | `Assets/GameModule/Common/Script/SpriteAtlasLateBinding.cs` |
| `StepDelaySequencer` | 多步骤延迟串行执行 | `Enqueue` / `StartAsync` / `Stop` / `Clear` | `Assets/GameModule/Common/Script/StepDelaySequencer.cs` |
| `GameSceneSwitchCoordinator` | 场景切换流程与异步加载 | `EnterGameLevelWithOverlay` / `BackToMainSceneWithOverlay` / `BackToEntrySceneWithOverlay` | `Assets/GameModule/Common/Script/GameSceneSwitchCoordinator.cs` |
| `SceneCleanupCoordinator` | 切场统一清理：KillAll→动画/View/Spine→AnimatorManager→运行态→CloseAll→对象池 | `CleanupBeforeSceneSwitch` / `AnimatorManager.ClearAllForSceneSwitch` / `ReleaseViewsForSceneSwitch` | `Assets/GameModule/Common/Script/SceneCleanupCoordinator.cs` |
| `ReturnToLobbyFlowManager` | 统一“返回大厅”流程入口 | `StartReturnFlow` | `Assets/GameModule/Common/Script/ReturnToLobbyFlowManager.cs` |
| `TimerDailyResetSyncHelper` | 跨天后本地计数字段重置与延迟同步 | `TryResetDailyPurchaseCounts` / `DelayRemoteSyncAsync` | `Assets/GameModule/Common/Script/TimerDailyResetSyncHelper.cs` |
| `ActivityEntryHelper` | 活动入口位左右分配与文案描述 | `GetLeftEntries` / `GetRightEntries` / `GetDescription` | `Assets/GameModule/Common/Script/ActivityEntryHelper.cs` |
| `RewardStringParser` | 奖励串/分组字符串解析；PlayOn Offer `|` 池 | `TryParseEntries` / `TryParseRewards` / `TryParseDailyRewardGroups` | `Assets/GameModule/Common/Script/RewardStringParser.cs` |
| `RedDotManager` | 全局红点数量缓存与变更广播（含头像/头像框状态红点） | `SetCount` / `GetCount` / `GetTotalCount` / `RefreshAvatarAndHeadBoardRedDotCount` / `UnlockAvatarAndHeadBoardByLevel` | `Assets/GameModule/Common/Script/RedDotManager.cs` |
| `CommonUtil` | 通用 UI/解锁条件辅助 | `IsUnlocked` / `GetPlayerLevel` / `RefreshGridContentAlignment` / `FormatUserCoin` | `Assets/GameModule/Common/Script/Model/CommonUtil.cs` |
| `CoinEconomyUtil` | 金币经济：对外仅发奖/花币两个放大入口；细则见 `Coin_Economy_Logic.md` | `ScaleReward` / `ScaleCost` | `Assets/GameModule/Common/Script/Model/CoinEconomyUtil.cs` |
| `FlyRewardConfig` / `FlyRewardConfigProvider` | 飞金币局内/局外 Profile | `ResolveInLevel` / `ResolveOutLevel` / `Config` | `Assets/GameModule/Common/Script/FlyRewardConfig.cs` |
| `UiRewardFlyTween` | 单物体飞向目标：Curve / ParabolaSolved | `FlyWorld` / `FlyWorldSolved` | `Assets/GameModule/Common/Script/UiRewardFlyTween.cs` |
| `UiRewardBurst` | 多物体八向扩散爆炸 | `PlayOneAsync` | `Assets/GameModule/Common/Script/UiRewardBurst.cs` |
| `UiRewardMultiCoinFly` | 多币飞编排：换算档 → 飞币数 / 间隔 + Burst + FlyTween | `ResolveVisualCount` / `PlayAsync` | `Assets/GameModule/Common/Script/UiRewardMultiCoinFly.cs` |
| `UiInverseTextureMask` | 全屏遮罩 + sourceImage 图形挖透明洞/点穿，可按需回调洞区点击 | `SetSourceImage` / `SetHoleClickDetection` | `Assets/GameModule/Common/Script/UI/UiInverseTextureMask.cs` |
| `CurrencyNumItem` | 弹板顶栏货币条基类：数值滚动 + appear/close/idle；`AddDelta` 按逻辑目标累加（勿用未完成滚动的显示值）；`SetBgWidth` 控制背景宽度；`SetAddButtonVisible` 控制加号按钮显隐 | `Init` / `PlayAdd` / `AddDelta` / `WhenValueAnimComplete` / `SnapToCloseEnd` / `PlayAppear` / `PlayClose` / `SetBgWidth` / `SetAddButtonVisible` | `Assets/GameModule/Common/Script/UI/CurrencyNumItem.cs` |
| `UIBubble` | **气泡提示**：锚定某点弹出；`Init(text, parent, pos, side)`；scale 0→1 appear→idle→1→0 close（默认 0.5/3/0.3）；托管回池 | `Init` / `BindRecycle` / `Close` / `ForceDestroy` | `Assets/GameModule/Common/Script/UI/UIBubble.cs` |
| `CommonPopToast` | **Toast / 吐丝提示**：短时浮动文案；挂独立 `UICanvas`（sortingOrder=2000）；Root CanvasGroup 渐显→idle→渐隐（默认 0.3/3/0.3）；可传 `onClosed` | `Init` / `BindRecycle` / `ForceDestroy` | `Assets/GameModule/Common/Script/UI/CommonPopToast.cs` |
| `CommonUIManager` | 公共小界面调度：气泡（`ShowBubble`）与吐丝（`ShowToast`→Canvas 2000）出池/回收 | `ShowBubble` / `ShowToast` / `CloseActiveToast` / `ClearActive` | `Assets/GameModule/Common/Script/UI/CommonUIManager.cs` |
| `BlastGameObjectPoolStore` | 通用 GameObject 对象池（Common）；出池必挂 parent+anchoredPosition | `Get` / `Put` / `ClearPath` / `ClearAll` | `Assets/GameModule/Common/Script/BlastGameObjectPoolStore.cs` |
| `CoinNumItem` / `LifeNumItem` / `AdNumItem` | 金币/体力/广告券子类（点击与动画前缀） | `RefreshFromUserData` / `PlayAddCoin` | `Assets/GameModule/Common/Script/UI/` |
| `PanelTopbarManager` | 按 `GamePanelConfig` 动态加载顶栏（默认挂第一个子节点，配置 `Focus_Node` 可指定挂载节点）；有入场则 Delay appear，无则直接 idle；关窗先等数字滚动再 close | `Setup` / `TryGetCoinItem` / `WhenValueAnimsComplete` / `PlayClose` / `Dispose` | `Assets/GameModule/Common/Script/UI/PanelTopbarManager.cs` |
| `DynamicTextMaterial` | TMP 描边/Face 运行时材质覆盖（Outline+Dilate） | `SetOutlineColor` / `SetOutlineThickness` / `SetFaceDilate` / `SetFaceSoftness` / `RefreshPreview` | `Assets/GameModule/Common/Script/DynamicTextMaterial.cs` |
| `AnimatorManager` | 统一动画播放通道（Spine/Animator/Timeline）与复用清理口径 | `PlaySpine` / `RestartSpine` / `PlaySpineThenQueue` / `IsSpineTrackPlaying` / `SetSpineSkin` / `PlaySpineWithHandle` / `ClearSpine` / `ClearSpineTrackForSwitch` / `ResetSpinePose` / `ResetSpineSlots` / `PlayAnimator` / `PlayTimeline` / `Pause` / `Stop` | `Assets/GameModule/Common/Script/AnimatorManager.cs` |

## Model 类

| 类名 | 路径 |
|---|---|
| `GameBaseModel` | `Assets/GameModule/Common/Script/Model/GameBaseModel.cs` |
| `TimedActivityBaseModel` | `Assets/GameModule/Common/Script/Model/TimedActivityBaseModel.cs` |

## UI*View 类

| 类名 | 路径 |
|---|---|
| `UIChangeSceneView` | `Assets/GameModule/Common/Script/UIChangeSceneView.cs` |

## Script 类清单（Common/Script）

| 类名 | 路径 |
|---|---|
| `ActivityEntryHelper` | `Assets/GameModule/Common/Script/ActivityEntryHelper.cs` |
| `AnimatorManager` | `Assets/GameModule/Common/Script/AnimatorManager.cs` |
| `AnimPlayHandle` | `Assets/GameModule/Common/Script/AnimatorManager.cs` |
| `AnimPlayMode` | `Assets/GameModule/Common/Script/AnimatorManager.cs` |
| `AnimChannel` | `Assets/GameModule/Common/Script/AnimatorManager.cs` |
| `BlastLevelGroupUtil` | `Assets/GameModule/Common/Script/BlastLevelGroup.cs` |
| `GameConst` | `Assets/GameModule/Common/Script/GameConst.cs` |

> 通用 UI/流程时间旋钮（刷新间隔、回大厅弹板延迟、跨天同步延迟、大厅通行证表演时长、道具 show 延迟 / 锤子吸收 PathCurve·总收集·逐块错峰衰减·终缩 / BlastAreaRoot 抬升·还原（各 duration+Ease）等）已迁入 `BlastUIRuntimeConfig`（`Common Timing` / `Home Pass Timing` / `HUD Timing` / `Prop Use UI`），经 `BlastUIRuntimeConfigProvider.UIConfig.Resolve*` 直读（配置必填，无空配置/硬编码时长兜底）；`GameConst` 仅保留路径、日刷偏移、空间偏移与广告位等非时长常量。
| `GameSceneSwitchCoordinator` | `Assets/GameModule/Common/Script/GameSceneSwitchCoordinator.cs` |
| `SceneCleanupCoordinator` | `Assets/GameModule/Common/Script/SceneCleanupCoordinator.cs` |
| `CommonUtil` | `Assets/GameModule/Common/Script/Model/CommonUtil.cs` |
| `CoinEconomyUtil` | `Assets/GameModule/Common/Script/Model/CoinEconomyUtil.cs` |
| `DynamicTextMaterial` | `Assets/GameModule/Common/Script/DynamicTextMaterial.cs` |
| `GameBaseModel` | `Assets/GameModule/Common/Script/Model/GameBaseModel.cs` |
| `GameModelManager` | `Assets/GameModule/Common/Script/Model/GameModelManager.cs` |
| `TempGameModelDocumentation` | `Assets/GameModule/Common/Script/Model/TempGameModel.cs` |
| `TimedActivityBaseModel` | `Assets/GameModule/Common/Script/Model/TimedActivityBaseModel.cs` |
| `PopUpManager` | `Assets/GameModule/Common/Script/PopUpManager.cs` |
| `ResourcesManager` | `Assets/GameModule/Common/Script/ResourcesManager.cs` |
| `SpriteAtlasLateBinding` | `Assets/GameModule/Common/Script/SpriteAtlasLateBinding.cs` |
| `ReturnToLobbyFlowContext` | `Assets/GameModule/Common/Script/ReturnToLobbyFlowManager.cs` |
| `ReturnToLobbyFlowManager` | `Assets/GameModule/Common/Script/ReturnToLobbyFlowManager.cs` |
| `RedDotManager` | `Assets/GameModule/Common/Script/RedDotManager.cs` |
| `RewardStringParser` | `Assets/GameModule/Common/Script/RewardStringParser.cs` |
| `SequencerStep` | `Assets/GameModule/Common/Script/StepDelaySequencer.cs` |
| `StepDelaySequencer` | `Assets/GameModule/Common/Script/StepDelaySequencer.cs` |
| `TimerDailyResetSyncHelper` | `Assets/GameModule/Common/Script/TimerDailyResetSyncHelper.cs` |
| `TimerManager` | `Assets/GameModule/Common/Script/TimerManager.cs` |
| `TimerTaskInfo` | `Assets/GameModule/Common/Script/TimerManager.cs` |
| `TopMask` | `Assets/GameModule/Common/Script/TopMask.cs` |
| `UiRewardMultiCoinFly` | `Assets/GameModule/Common/Script/UiRewardMultiCoinFly.cs` |
| `UiRewardMultiCoinFlySettings` | `Assets/GameModule/Common/Script/UiRewardMultiCoinFly.cs` |
| `UiRewardFlyTween` | `Assets/GameModule/Common/Script/UiRewardFlyTween.cs` |
| `UiRewardBurst` / `UiRewardBurstSettings` | `Assets/GameModule/Common/Script/UiRewardBurst.cs` |
| `AvatarChooseItem` | `Assets/GameModule/Common/Script/UI/AvatarChooseItem.cs` |
| `AvatarItem` | `Assets/GameModule/Common/Script/UI/AvatarItem.cs` |
| `CommonBuyBtn` | `Assets/GameModule/Common/Script/UI/CommonBuyBtn.cs` |
| `CommonBuyData` | `Assets/GameModule/Common/Script/UI/CommonBuyData.cs` |
| `UiInverseTextureMask` | `Assets/GameModule/Common/Script/UI/UiInverseTextureMask.cs` |
| `UIBubble` | `Assets/GameModule/Common/Script/UI/UIBubble.cs` |
| `CommonPopToast` | `Assets/GameModule/Common/Script/UI/CommonPopToast.cs` |
| `CommonUIManager` | `Assets/GameModule/Common/Script/UI/CommonUIManager.cs` |
| `BlastGameObjectPoolStore` | `Assets/GameModule/Common/Script/BlastGameObjectPoolStore.cs` |
| `CommonRedPoint` | `Assets/GameModule/Common/Script/UI/CommonRedPoint.cs` |
| `FrameChooseItem` | `Assets/GameModule/Common/Script/UI/FrameChooseItem.cs` |
| `RewardItem` | `Assets/GameModule/Common/Script/UI/RewardItem.cs` |
| `RewardItemViewDataBuilder` | `Assets/GameModule/Common/Script/UI/RewardItemViewDataBuilder.cs` |
| `CommonRewardView` / `CommonRewardViewOpenArgs` / `RewardTitleType` | `Assets/GameModule/Common/Script/UI/CommonRewardView.cs` |
| `CommonRewardViewBinder` | `Assets/GameModule/Common/Script/ViewBinder/CommonRewardViewBinder.cs` |
| `TopMaskBinder` | `Assets/GameModule/Common/Script/UI/ViewBinder/TopMaskBinder.cs` |
| `UIChangeSceneView` | `Assets/GameModule/Common/Script/UIChangeSceneView.cs` |
| `RemoveAdViewBinder` | `Assets/GameModule/Common/Script/ViewBinder/RemoveAdViewBinder.cs` |

## 快速定位

- 通用奖励弹窗：`UIManager.Open<CommonRewardView>(null, CommonRewardViewOpenArgs)`；View 刷新标题图和奖励格，Binder 只绑组件。标题图从 `CommonRewardTitleAtlas` 加载，奖励格按 3 列居中排列，12 个及以上启用纵向滚动。

- 气泡提示 / UIBubble / Bubble→`CommonUIManager.ShowBubble`（锚定弹出，scale 0→1→0，默认 0.5/3/0.3）
- Toast / 吐丝提示 / CommonPopToast→`CommonUIManager.ShowToast(text)`（独立 `UICanvas_2000`；CanvasGroup 渐显 idle 渐隐；可选 `onClosed`）；`CloseActiveToast` 提前关；切场景前 `ClearActive`
- GameObject 对象池 / PoolStore→`BlastGameObjectPoolStore`（`Assets/GameModule/Common/Script/BlastGameObjectPoolStore.cs`）
- 反向挖洞 / sourceImage 挖洞 / 点穿下层→`UiInverseTextureMask`（遮罩 Image 挂组件，拖 sourceImage）
- 飞金币多币编排 / 换算档（`ConvertTiers` + `MaxVisualCount`）/ 局内局外 Profile→`UiRewardMultiCoinFly` + `BlastSettlementCoinFly`；配置 `FlyRewardConfig`（`inLevel` / `outLevel`）
- 飞币 HUD 分段加数→`CurrencyNumItem.AddDelta`（逻辑目标累加，勿用滚动中未提交显示值）
- 真机图集 Sprite 全白 / `atlasRequested wasn't listened to`→`SpriteAtlasLateBinding.Register`（`GameMain.Init`）；新图集须登记 `AtlasNameToPath`
- TMP Label 描边/Face Dilate 被重置→`DynamicTextMaterial`（改组件字段，勿改临时材质 `TMP_Outline_Material_Editor`）；`OnEnable`/`LateUpdate`/`ApplyOutlineSettings` 须重绑 `fontSharedMaterial`（SetActive/关开节点/改字会丢；编辑态同样）
- TMP 描边不显示→克隆字体源材质（保留 Mobile/SSD Shader），勿硬编码 `Shader.Find(Distance Field)`；重绑时勿用字体默认值覆盖 Outline/Face 字段
- TMP 外描边游戏切边、Scene 正常→`DynamicTextMaterial.ApplyOutlineSettings` 需 `UpdateMeshPadding` + `extraPadding`；仍切则检查字体 `Atlas Padding`

## 头像与头像框公共 UI 组件

- `AvatarItem`：展示头像图片，并根据 `isDynamic` 按 `UIStateToggle.ExclusiveObjects` 下标 `0=Static`、`1=Dynamic` 切换状态。
- `FrameItem`：展示头像框图片，并按 `UIStateToggle.ExclusiveObjects` 下标 `0=Static`、`1=Dynamic` 切换静态/动态状态，同时管理限时标记和锁定标记。
- `UserAvatarItem`：组合 `AvatarItem` 与 `FrameItem`，供主页 Top 和 Profile 顶部预览复用。
- `AvatarChooseItem` / `FrameChooseItem`：列表单元格外壳，负责选中/锁定状态和点击回调；按钮监听只绑定一次，`RefreshItem` / `RefreshView` 只更新当前回调。
- `UIStateToggle`：切换公共 UI 子节点；头像和头像框使用 `ExclusiveGroup` 下标切换（`0=Static`、`1=Dynamic`），登录失败平台图标等自定义状态仍可按状态名切换。

## 返回主入口

- [GameModule 多 Agent 代码导航总纲](../gamemain-class-function-index.md)
