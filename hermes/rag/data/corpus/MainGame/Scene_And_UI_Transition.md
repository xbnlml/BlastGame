# Scene And UI Transition（场景与壳层 UI）


## 切场职责分层

| 类/文件 | 职责 |
|---|---|
| `GameSceneSwitchCoordinator` | 入局/回主场景导航、遮罩与异步加载编排 |
| `SceneCleanupCoordinator` | 切场前统一清理（动画、视图、运行态、池） |
| `UIChangeSceneView` | 切场遮罩；`OverlayStyle` 切换根下两个子物体 |
| `UIManager` | 壳层窗口栈生命周期管理，并提供窗口打开/关闭/CloseAll 钩子 |
| `BlastUIManager` | 管理 `Panel_Priority >= 0` 弹板的唯一显示、优先级恢复与切场清理 |

## 协作边界

- 场景层只负责“切去哪+怎么切”，不负责关卡规则初始化。
- 主场景加载成功后先完成主流程回调，再触发登录弹板队列；广告模块在主场景就绪后延后初始化，避免阻塞首屏进入。
- 清理顺序固定：Kill tween -> 释放视图/动画 -> 清运行态 -> CloseAll -> 清对象池。
- `ReleaseViewsForSceneSwitch` 必须先于 `CloseAll`，避免窗口关闭后丢失解绑时机。
- 清对象池走 `BlastGameObjectPoolLifecycle.ClearAllIfAlive` → `HaveInstance`/`Instance.ClearAll`；禁止 `FindObjectOfType`（`SingletonMono` 带 `HideFlags.DontSave`，Find 会漏掉）。
- `PrepareSceneSwitch(style)`：先开 `UIChangeSceneView` → `CleanupBeforeSceneSwitch`（含 `CloseAll`）→ 再开遮罩；两次 Open 都带 `OverlayStyle`（CloseAll 后需重新应用）。
- 遮罩子物体口径：`EnterFromMain` 显示子物体1（`Bg`，主界面进关）；`ReturnOrReload` 显示子物体2（`Bg (1)`，回主界面 / 重载关卡）。大厅 `UIHomeLevelView` 默认 `EnterFromMain`；`BackToMainSceneWithOverlay` / 胜利未解锁重进 / HUD 跳关传 `ReturnOrReload`。
- 返回主场景时，场景异步加载成功只代表资源加载完成；必须继续保留 `UIChangeSceneView`，收到 `OnGameMainUiReady` 后才关闭遮罩并执行完成回调。加载失败则立即关闭遮罩并结束切换。

## 生命周期约束

- 所有入口（进关/回主场景/重入）都走同一清理编排，禁止绕过。
- 切场恢复后由关卡加载链路重新绑定视图，不继承上局临时态。

## 适用范围

说明大厅、关卡场景和壳层窗口之间的切换，以及局内视图解绑。局内玩法见 [`Gameplay_Flow_Logic.md`](Gameplay_Flow_Logic.md)。

## 1. 进入关卡

```text
Home / Level UI
  → entry request
  → health / level validation
  → GameSceneSwitchCoordinator
  → GameMain init
  → BlastLevelEntry
```

场景切换层只负责导航、遮罩和完成回调；关卡数据由 GameMain 初始化。

## 2. 返回大厅

```text
Win / Lose / abandon
  → settlement or abandon handling
  → UnbindViews / release level resources
  → GameSceneSwitchCoordinator
  → Home UI refresh
```

返回前必须释放当前关卡配置、Presenter 绑定、动画、timer 和临时对象。

## 3. 窗口职责

- `UIGameMainView`：局内窗口和视图绑定。
- `UIGameWinView`：胜利结算和领奖分流。
- `UIGameLoseView`：失败结算与重试/返回入口。
- `UIGameContinueView`：槽位满续命确认（金币 Play On / FailOffer 售卖板）。
- `UIManager`：通用窗口生命周期与窗口生命周期钩子。
- `BlastUIManager`：通过 `PanelPriorityDic` / `CurrentPanel` 管理受配置约束的 Blast 弹板；新弹板出现前强制关闭旧弹板，用户关闭高优先级弹板时恢复更低优先级弹板。

窗口只负责展示和用户意图，不直接推进玩法状态。

## 4. 代码入口

| 问题 | 入口 |
|---|---|
| 场景切换 | `GameSceneSwitchCoordinator` |
| 进关请求 | `BlastLevelEntry` / Home `LevelUIView` |
| 局内解绑 | `BlastGameViewPresenter.UnbindViews` |
| 胜利返回 | `UIGameWinView` |
| 失败续命弹板 | `UIGameContinueView` / `BlastPowerUpConfirm.RequestFailReviveTempSlots` |
| 局内道具购买 | `UIGamePropBuyView` / `BlastPowerUpConfirm.RequestPowerUpPurchase` |
| 失败结算 | `UIGameLoseView` / `BlastGameController.State` |
| 通用窗口 | `Doc/Tools/UIManager_Usage.md` |
| Blast 弹板唯一显示 | `BlastUIManager` / `BlastUIWindowView` |
