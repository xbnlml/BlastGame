# Common Runtime Infrastructure

## 摘要

- 本文是 `Assets/GameModule/Common/` 运行时基础设施统一入口。
- 目标：让各模块优先复用 `Common` 能力，避免重复实现通用逻辑。
- 详细实现仍以下游专题文档为准，本文仅维护职责边界与入口索引。

## 资源加载：ResourcesManager

- 代码入口：`Assets/GameModule/Common/Script/ResourcesManager.cs`
- 职责：
  - 统一资源加载入口，透传 `ResourceHub` 常用能力。
  - 提供便捷方法（如 `LoadTexture` / `LoadSpriteAtlas`）。
  - 维护常驻缓存规则：精确白名单（例如 `RewardItemAtlas`）+ `Assets/GameModule/**/Config/`、`Assets/GameModule/**/Prefabs/` 路径默认常驻 + `Assets/GameModule/**/*.spriteatlasv2` 图集常驻。
- 约束：
  - 业务层资源加载统一走 `ResourcesManager`。
  - 业务代码不再直接调用 `ResourceHub`。
  - 静态配置与通用预设优先放在 `Config/`、`Prefabs/` 目录下，复用默认常驻规则；临时资源不要放进这两个目录以免常驻占用内存。

## 通用奖励弹窗：CommonRewardView

- 代码入口：`Assets/GameModule/Common/Script/UI/CommonRewardView.cs`
- 打开：`UIManager.Open<CommonRewardView>(null, new CommonRewardViewOpenArgs { Rewards, TitleType })`。
- View 按打开参数刷新标题图和奖励格；`CommonRewardViewBinder` 只绑组件。标题从 `CommonRewardTitleAtlas` 按 `tyhd_bt1`～`tyhd_bt5` 覆盖显示。
- 奖励格按 256 大小、横向间距 90、纵向间距 70 排列，每行最多 3 个；12 个及以上开启纵向滚动。

## SpriteAtlas 晚绑定：SpriteAtlasLateBinding

- 代码入口：`Assets/GameModule/Common/Script/SpriteAtlasLateBinding.cs`
- 注册时机：`GameMain.Init` 开头（ResourceHub 已可用、业务 UI 加载之前）。
- 职责：监听 `SpriteAtlasManager.atlasRequested`，按图集名加载对应 `.spriteatlasv2` 并回调给 Unity。
- 真机症状：未注册时日志 `SpriteAtlasManager.atlasRequested wasn't listened to while XXX requested`，对应图集 Sprite 全白。
- 约束：
  - 新增 `.spriteatlasv2` 必须在 `AtlasNameToPath` 登记（key = 资源文件名不含扩展名）。
  - 图集经晚绑定注入后由 `ResourcesManager` 常驻，禁止卸载。
  - Editor Simulation 也可能不触发该回调；以 Android/iOS 真机或非 Simulation 包为准验证。

## 定时系统：TimerManager

- 代码入口：`Assets/GameModule/Common/Script/TimerManager.cs`
- 文档入口：`Doc/Tools/TimerManager_Usage.md`
- 职责：
  - 提供循环、延时、倒计时、截止型计时能力。
  - 统一 `timerId` 生命周期管理与 owner 级清理。
- 约束：
  - UI/模块销毁时必须移除相关 timer，避免悬挂回调。
  - 列表场景优先“列表级单 timer”，避免 item 级泛滥注册。
  - 跨天轮询间隔、跨天远程同步延迟、体力倒计时刷新间隔统一读 `BlastUIRuntimeConfig`（`refreshIntervalSeconds` / `remoteSyncDelaySeconds`）；主界面活动倒计时按秒立即刷新并使用 `UtilsTimeString.TimeString2` 格式。

## 模型总管：GameModelManager

- 代码入口：`Assets/GameModule/Common/Script/Model/GameModelManager.cs`
- 文档入口：`Doc/MainGame/Game_Model_Logic.md`
- 职责：
  - 管理活动/模块模型注册、初始化、查询与生命周期。
  - 统一 `GameBaseModel` / `TimedActivityBaseModel` 协作入口。
- 约束：
  - 模块数据写入应经模型层收口，不在 UI 侧直接改 Profile 状态。

## 通用购买按钮：CommonBuyBtn

- 代码入口：
  - `Assets/GameModule/Common/Script/UI/CommonBuyBtn.cs`
  - `Assets/GameModule/Common/Script/UI/CommonBuyData.cs`
- 职责边界（统一约定）：
  - `CommonBuyBtn` 只负责“点击 -> 调用 `PurchaseSystem.Instance.Purchase(...)`”。
  - 业务模块（Model）负责 `PurchaseSystem.Register/UnRegister` 与购买成功后的状态刷新。
  - UI 不直接修改模块状态或 Profile 数据。
- 接入步骤（推荐）：
  - 在业务 UI 初始化时，给 `CommonBuyBtn.SetBuyData(...)` 传入 `purchaseId/guid/rewards/userData`。
  - 在对应模块 Model 生命周期内注册支付回调（`AddActivityEvent` / `RemoveActivityEvent`）。
  - 在模块回调中按 `purchaseId` 路由，完成模块内数据更新并触发 UI 刷新。
- 约束：
  - 不在 `CommonBuyBtn` 内写模块业务刷新逻辑，避免 Common 组件与模块耦合。
  - 各模块保持“点击通用、刷新归模块”的一致模式，便于后续新增购买入口复用。

## 步骤编排：StepDelaySequencer

- 代码入口：`Assets/GameModule/Common/Script/StepDelaySequencer.cs`
- 文档入口：`Doc/MainGame/StepDelaySequencer_Usage.md`
- 职责：提供“串行步骤 + 可选延时 + 可取消”的轻量流程编排能力。
- 约束：
  - 启动前先 `Clear`，避免旧步骤残留。
  - UI 关闭/切场景时执行 `Stop + Clear`，避免悬挂异步流程。
  - `ReturnToLobbyFlowManager` 弹板步骤延迟读 `BlastUIRuntimeConfig.returnToLobbyPopupStepDelaySeconds`。

## 通用飞行动画（三层）

- 代码入口：
  - `Assets/GameModule/Common/Script/UiRewardFlyTween.cs`（单物体飞向目标：Curve / ParabolaSolved）
  - `Assets/GameModule/Common/Script/UiRewardBurst.cs`（多物体八向扩散爆炸）
  - `Assets/GameModule/Common/Script/UiRewardMultiCoinFly.cs`（编排：换算档 → 飞币数 / 间隔 + Burst + FlyTween）
  - `Assets/GameModule/Common/Script/UiRewardFlyTweenCurveTestDriver.cs`（编辑器调试 Curve / ParabolaSolved）
- 职责：
  - 单飞：锤子等可用 PathCurve；动物/槽位/金币飞终点走 `FlyWorldSolved`。
  - 爆炸：Track5 八向扩散（世界坐标距离，局内约 0.4~0.8）。
  - 多币飞：`ConvertTiers` 按奖励取 `CoinsPerVisual`，`visualCount = clamp(ceil(a/c), 1, MaxVisualCount)`，末枚补余；再起飞间隔 → 爆炸 → 抛物线飞终点；单枚到达即隐藏，壳层 Destroy。
- 约束：
  - 通用算法归 `Common`；业务壳 `BlastSettlementCoinFly` 选局内/局外 Profile；配置真源 `FlyRewardConfig`（`Assets/GameModule/Common/ConfigSo/FlyRewardConfig.asset`）。
  - prefab：`BlockCoinSpine`。
  - `Resolve*` / Provider 返回配置对象本体（非克隆），运行时改值会对后续调用全局生效。
  - 多币飞使用 `UiRewardMultiCoinFly` 的分档与视觉数量计算；配置位于 `FlyRewardConfig`，不依赖 `BlastUIRuntimeConfig`。

## 场景切换：GameSceneSwitchCoordinator

- 代码入口：`Assets/GameModule/Common/Script/GameSceneSwitchCoordinator.cs`
- 文档入口：`Doc/MainGame/Scene_And_UI_Transition.md`
- 职责：主界面 ↔ 关卡场景遮罩、异步 `LoadScene`、Transient 对象池白名单清理；与 `BlastGameController.LoadLevel` 衔接。

## 贴图 alpha 反向挖洞：UiInverseTextureMask

- 代码入口：`Assets/GameModule/Common/Script/UI/UiInverseTextureMask.cs`
- 逻辑：全屏半透遮罩 + `sourceImage` 用 Stencil 写洞（九宫格由 Image 自己网格处理，组件不手算 UV）。洞不显示 source 图，只露出并点穿下层。
- 接入：遮罩 Image 挂组件，拖 `sourceImage`。source 会自动提到与 mask 同级且先画。
- `passThroughInHole`：默认 true（洞内点穿）；引导目标点击可设 false，由遮罩收点击。
- `detectHoleClick`：默认关闭；需要洞区点击能力的调用方通过 `SetHoleClickDetection(true, callback)` 开启并注册回调，结束时传 `false, null` 清理。非点穿模式在洞内按下时回调；点穿模式等待洞内抬起，让底层 UI 先完成点击。
- source 贴图不可读时，点击检测按 source 的矩形范围降级，避免写入 `alphaHitTestMinimumThreshold` 触发 Unity 异常；需要精确透明度点击时开启 Read/Write。
- Shader：`UI/InverseTextureMask`（遮罩）+ `UI/InverseTextureMaskHole`（写洞，硬编码 ColorMask 0 + Blend Zero One）；运行时 `Shader.Find` 建材质，不依赖额外材质球。
- **真机必检**：两个 Shader 须在 `ProjectSettings/GraphicsSettings` Always Included；否则 `Shader.Find` 在包内为空，sourceImage 会用默认 UI 材质画出深色不透明块（Editor 正常、真机异常）。
- 洞区仍不透明时：先看真机日志是否有 `[UiInverseTextureMask] Shader ... not found`；再确认 source 与 mask 同级且先画。

## 维护规则

- 新增 `Assets/GameModule/Common/` 通用能力时，先补充本文入口与边界说明。
- 若新增能力已形成稳定使用规范，再新增对应专题文档并在本文挂链接。
