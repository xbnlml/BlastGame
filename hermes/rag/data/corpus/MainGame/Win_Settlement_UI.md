# Win Settlement UI

胜利结算页（`UIGameWinView`）展示、领奖分流与飞金币。

## 打开与入场

- `EnterWinState`：`TakeLevelTempCoin` + 星级奖励合计为 `baseReward`，先 `AddCoins(base, false)`，再 `QueuePendingWinView(base, stars)`。
- `TryShowPendingWinView`：等攻击飞 / landing / close 视觉收尾后再延迟 1s `Open<UIGameWinView>(null, reward, stars)`（**不用**逻辑 `_bullets` 门禁；`Ended` 后不再 TickCombat）。
- Appear：`Tim_UIGameWinView_appear{N}`，`N = Clamp(stars, 1, 3)`（Timeline 模式）。
  - Prefab 可为独立命名节点，或单 `PlayableDirector`（如 `SafeArea`）按 asset 名切换。
- Close：无 `Tim_UIGameWinView_close`；`TryPlayCustomCloseAnimation` 跳过 Timeline，直接收窗（无 Fade）。
  - 主页未解锁领奖后：飞币 → `GameSceneSwitchCoordinator.EnterGameLevelWithOverlay(overlayStyle: ReturnOrReload)`（`UIChangeSceneView` 显示子物体2，`CloseAll` 收胜利页，再重载 `GameLevelScene`；`Profile.Level` 已在 `EnterWinState` 推进）。
- 展示：
  - `StarItems`：按星数显示前 N 个并点亮
  - `StarBgObj`（`GreatBg`/`PerfectBg`/`ExcellentBg`）：按 `CurrentLevelDifficulty`（0/1/2）单选；0 星不显示
  - 激活背景标题：按星级替换为 `Great` / `Fantastic` / `Excellent`（只改文本，描边颜色继续跟当前难度背景材质）
  - `LevelTipObj`：按 `CurrentLevelDifficulty`（0/1/2）单选
  - `CoinNumItem.Init`（经 `PanelTopbar.TryGetCoinItem`）：发奖前金币 = `Profile.Coin - baseReward`（文案走 `CommonUtil.FormatUserCoin`）
  - 按钮文案：`Collect\r\n<sprite=0> {base}` / `Double Coins\r\n<sprite=0> {base*2}`
  - `baseReward` = 星级通关金币 + 本关 Objective 局内临时金币（`LevelTempCoin`）

## 结算按钮

- `CommonUtil.IsUnlocked(BlastActivityType.ADS)`：
  - 未解锁 → 仅 `CollectBtn`
  - 已解锁 → `CollectBtn2` + `DoubleCoinsBtn`
- `NextLevelBtn` 正式流隐藏。
- 双倍：`ADManager.TryShowAdOrUseCoupon(Rewarded, RV_WinDoubleCoins)`（有券弹 `RemoveAdView`，无券直接播广告）；成功 → 双倍领奖；失败/关闭/未开播 → 只恢复按钮。

## 领奖分流

| 条件 | 行为 |
|---|---|
| 主页已解锁 | 先 `ActContent.SetActive(false)` 清弹板中间；`ReturnToLobbyFlowManager.StartReturnFlow`；大厅 `BlastSettlementCoinFly` 从 `UIHomeLevelView.GetCoinFlyStart()`（`FlyCoinStartRect`）飞向 `TopUIView.GetCoinFlyTarget()`；弹板步骤延迟读 `BlastUIRuntimeConfig.returnToLobbyPopupStepDelaySeconds` |
| 主页未解锁 | **保留**弹板中间 `ActContent`/`CoinsRewardItem`，以其周围为起点本页飞向 `PanelTopbar` 的 `CoinNumItem` → `PlayAddCoin(Profile.Coin)` → `EnterGameLevelWithOverlay(ReturnOrReload)`（`UIChangeSceneView` 子物体2 + 重载 GameLevelScene）；双倍时先补发一份 `AddCoins(base, true)` |

主页解锁口径：`Profile.Level >= DataConfig.openMainScene`。

## 飞金币

- 预设：`Assets/GameModule/GameMain/Effect/Prefabs/BlockCoinSpine.prefab`（每枚飞币一实例，按换算档算出的飞币数动态 Instantiate）
- 业务壳：`BlastSettlementCoinFly.PlayAsync(parent, start, end, rewardAmount, CoinFlyScene, …, onCoinArrived)`
- 通用算法：`UiRewardMultiCoinFly`（换算档 → 飞币数 + 间隔 + `UiRewardBurst` 八向爆炸 + `UiRewardFlyTween.FlyWorldSolved`；到达即隐藏）
- HUD 数字：`onCoinArrived` → `CoinNumItem.AddCoinDelta`；`CurrencyNumItem` 用逻辑目标累加 delta（到达间隔常小于滚动时长；若按未提交显示值累加，会反复只加一档 `CoinsPerVisual`，表现为奖励 25 却只看到 +2/+4）
- 配置：`Assets/GameModule/Common/ConfigSo/FlyRewardConfig.asset`（`FlyRewardConfigProvider.Config`）
  - 局内：`inLevel` ← `CoinFlyScene.InLevel`（Objective、未解锁主页本页飞）
  - 局外：`outLevel` ← `CoinFlyScene.OutLevel`（回大厅）
  - 换算 / 上限 / 爆炸 / 轨迹：`ConvertTiers` / `MaxVisualCount` / `Burst` / `Parabola`
  - 默认档：`1–9→c1` / `10–49→c2` / `50–99→c5` / `100+→c10`，`MaxVisualCount=20`；末枚补余到真实奖励总额
- 出实例：`ResourcesManager.InstantiateGameObject` 挂 parent，播完 `Destroy`；禁止 `LoadAsset<GameObject>` 再 `Instantiate`

## 关键类

| 类 | 路径 |
|---|---|
| `UIGameWinView` | `Assets/GameModule/GameMain/Script/UI/UIGameWinView.cs` |
| `PanelTopbarManager` | `Assets/GameModule/Common/Script/UI/PanelTopbarManager.cs` |
| `CurrencyNumItem` / `CoinNumItem` | `Assets/GameModule/Common/Script/UI/` |
| `BlastSettlementCoinFly` | `Assets/GameModule/GameMain/Script/Runtime/BlastSettlementCoinFly.cs` |
| `ReturnToLobbyFlowManager` | `Assets/GameModule/Common/Script/ReturnToLobbyFlowManager.cs` |
| `TopUIView.GetCoinFlyTarget` | `Assets/GameModule/HomeModule/Script/UI/TopUIView.cs` |
| `UIHomeLevelView.GetCoinFlyStart` | `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelView.cs`（锚点 `FlyCoinStartRect`） |
| `UiRewardMultiCoinFly` | `Assets/GameModule/Common/Script/UiRewardMultiCoinFly.cs` |
| `FlyRewardConfig` | `Assets/GameModule/Common/Script/FlyRewardConfig.cs` / `ConfigSo/FlyRewardConfig.asset` |
| `UiRewardBurst` | `Assets/GameModule/Common/Script/UiRewardBurst.cs` |
| `UiRewardFlyTween` | `Assets/GameModule/Common/Script/UiRewardFlyTween.cs` |
| `TopUIView` 分段刷币 | `BeginCoinFlyPresentation` / `ApplyCoinFlyDelta` / `EndCoinFlyPresentation` → `PanelTopbar` `CoinNumItem` |
