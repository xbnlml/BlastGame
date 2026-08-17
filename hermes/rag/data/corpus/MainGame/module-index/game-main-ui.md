# GameMain UI / 视图索引

## 用途

从“Board、Stage、Slots、HUD、动画、对象池、结算 UI”类提示词定位视图入口与类职责。

| 关键词 | 首选入口 | 专题 |
|---|---|---|
| 局内视图总编排 | `BlastGameViewPresenter` | `GM_Board_Stage_Flow.md` |
| Board 刷新 | `BlastBoardView` | `GM_Board_Stage_Flow.md` |
| Stage 候选区 | `BlastStageView` / `BlastStageCellView` | `GM_Board_Stage_Flow.md` |
| Slots 槽位 | `BlastSlotsView` / `BlastSlotCellView` | `GM_Board_Stage_Flow.md` |
| Stage/Slot 动物动画 | `BlastStageAnimalView` / `BlastStageAnimalPool` | `Stage_Animal_Animation_Playback.md` |
| 线条与飞行动画 | `BlastEffectsView` / `BlastLineEffectView` | `GM_Board_Stage_Flow.md` |
| Board→Slot AttackFly（idle / 先下再拐 / 终缩 / 落点） | `BlastGameViewPresenter` + `UIGameMainEffectLayerController.SlotsCellRootDown`（=`BlastSlotsView.CellRootDown`）+ `BlastUIRuntimeConfig`「Slot Attack Animal Motion」（`slotAttackAnimalFlySettings` DownDistance / `boardToSlotFlyEndScaleFactor` / `boardToSlotFlyEndScaleCurve` / `boardToSlotFlyEndLocalOffset`；Objective 金币仍挂 `BoardViewUp`，命中态层级由 `AttachObjectiveHitSpineToBoardViewUp` / `BringObjectiveAttackCoinToFront` 控制） | `Playbooks/game-main/ui.md` |
| HUD、星级、进度 | `BlastHudView` / `BlastLevelProgressView` | `Game_Score_Logic.md` |
| 胜利结算 | `UIGameWinView` | `Win_Settlement_UI.md` |
| 失败与续命 UI | `UIGameContinueView` / `UIGameLoseView` | `Gameplay_Flow_Logic.md` / `PlayOn_Offer_Logic.md` |
| 中途退出确认 | `UIGameExitView` / `BlastMainSettingView` | `Gameplay_Flow_Logic.md` |
| 道具弹板 | `BlastPropUseUiSession` / `BlastPowerUpView` / `UIGamePropBuyView` | `POWERUP-SYSTEM-Unity.md` |
| 场景和窗口框架 | `UIGameMainView` / `UIManager` / `BlastUIManager` / `BlastUIWindowView` | `Scene_And_UI_Transition.md` / `Doc/Tools/UIManager_Usage.md` |
| 弹板顶栏 / Topbar / CoinNumObj / LifeNumObj / AdNumObj | `PanelTopbarManager` / `CurrencyNumItem` | `GamePanelConfig` + `common.md` |

## 目录分层

- `Script/UI/`：View/Binder 与窗口层。
- `Script/Runtime/`：视图编排、对象池、连线/飞出/放置动画协作。
- `Script/Visual/`：无状态视觉数据拼装。
- 规则与状态归 Runtime/Sim，UI 不复制业务判定。

## 视图主链路

`Controller state change → Presenter dirty/delta → Board / Slots / Stage → Effects / HUD`

## 核心类职责

| 类 / 文件 | 职责 | 协作者 |
|---|---|---|
| `BlastUIManager` | 管理 `Panel_Priority >= 0` 弹板唯一显示；新弹板出现前强制关闭旧弹板，高优先级用户关闭时按优先级恢复低层弹板，切场景清空状态 | `UIManager` / `GamePanelConfig` |
| `BlastUIWindowView` | 窗口基类：入退场动画（`CommonAnimator` 遍历子节点查找包含目标状态的 `Animator`，不依赖节点名称或顺序）；`Close()` 默认先交给 `BlastUIManager` 判断，再等 `PanelTopbar` 数字滚动并播退场；`Close(true)` 跳过退场；close 资源缺失退回直接收窗；切场景 `CloseAll`→`OnClose` 只 Dispose 不播 close | Binder / CanvasGroup / `PanelTopbarManager` / `BlastUIManager` |
| `BlastGameViewPresenter` | 局内视图总编排，消费 runtime delta | Board/Stage/Slots/HUD/Effects |
| `UIGameMainView` | 局内窗口容器与绑定 | Presenter / EffectLayerController |
| `BlastBoardView` | 盘面展示与运行期差量渲染 | Presenter / BoardCell |
| `BlastStageView` | 候选区渲染与交互入口 | StageCell / StageAnimal |
| `BlastSlotsView` | 槽位渲染门面与生命周期 | `BlastSlots*` 协作器 |
| `BlastEffectsView` | 线条、飞行与特效层 | LineEffect / PlacementAnim |
| `BlastHudView` / `BlastLevelProgressView` | 分数、进度与关卡信息 | Presenter |
| `UIGameWinView` / `UIGameLoseView` | 胜负结算窗；顶栏货币走 `PanelTopbar` | Scene / `CoinNumItem` |
| `UIGameExitView` / `BlastMainSettingView` | 局内设置与主动退出确认；`ExitBtn` 未达 `MainSceneUnlockLevel` 时隐藏；Exit 顶栏可配 `LifeNumObj` | AbandonLevel |
| `BlastPowerUpView` / `BlastPropUseUiSession` / `UIGamePropBuyView` | 道具入口、购买弹板与使用会话；锁定 tip → `ShowBubble(effectRect, lockBtnPos, text, side)`（道具1左/2·3中/4右） | PowerUps / PropUseViews / `common.md` |

## UI 协作者

| 类 | 职责 |
|---|---|
| `UIGameMainEffectLayerController` | Board/Slot/Stage 特效挂层；Board→动物飞挂 `SlotsCellRootDown`；Objective 命中态罐子沉底、金币置顶 |
| `BlastSlotsLinkEffectController` | 槽位连线生命周期 |
| `BlastSlotsCloseFlyController` | 槽位 close 飞出 |
| `BlastSlotsDisplayAmmoTracker` | 显示弹药跟踪 |
| `BlastSlotsTempAreaPresenter` | Temp 压缩与 fail-revive 视觉 |
| `BlastSlotsPieceVisualApplier` | piece 视觉 Apply |
| `BlastSlotsCellPool` | Cell 池 / seat 对齐 |
| `BlastStageAnimalPool` | Stage/Slot 动物对象池 |
| `BlastStagePlacementAnim` | Stage→Slot 放置动画 |
| `BlastSettlementCoinFly` | 结算飞金币 |
| `BlastBoardSpinePool` | Board Cell Spine 池 |
| `BlastBoardCellVisualDataBuilder` / `BlastBoardCellSnakeAnimResolver` | Board 视觉数据与蛇身动画解析 |

## 代码目录

- `Assets/GameModule/GameMain/Script/UI/`
- `Assets/GameModule/GameMain/Script/Visual/`
- `Assets/GameModule/GameMain/Script/Runtime/`（视图协作者）
