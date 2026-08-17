# GameMain 模块代码导航

## 适用范围

用于按关键词定位 `Assets/GameModule/GameMain/` 的当前代码入口。本文只做分层导航，不展开类职责与玩法规则。

## 模块分层

| 层 | 职责 | 首选入口 | 细分索引 |
|---|---|---|---|
| Runtime | 关卡会话、主循环、状态编排、回放、视图桥接 | `BlastGameController` | [`game-main-runtime.md`](game-main-runtime.md) |
| Sim | 攻击、放置状态、下落、队列、难度应用 | `BlastGameLogic` / `BlastEngine` | [`game-main-sim.md`](game-main-sim.md) |
| Level | 配置解析与运行态初始化 | `BlastLevelLoader` / `BlastGameLevelSession` | [`game-main-level-core.md`](game-main-level-core.md) |
| UI | Board、Stage、Slots、HUD 和动画 | `BlastGameViewPresenter` | [`game-main-ui.md`](game-main-ui.md) |
| Core | 共享数据模型与纯逻辑 | `BlastTypes` / `BlastScorePureLogic` | [`game-main-level-core.md`](game-main-level-core.md) |

先选层看 [`game-main-agent-index.md`](game-main-agent-index.md)，再进上表细分页。

## Runtime 入口（摘要）

| 类 / 文件 | 关键职责 | 代码入口 |
|---|---|---|
| `BlastGameController` | 固定时间步驱动主循环，协调 State / Stage / Slots / UI | `Runtime/BlastGameController.cs` |
| `BlastGameController.Loading` | 关卡加载 facade | `LoadLevel` |
| `BlastGameController.Gameplay` | Update、战斗反馈、连击、回放推进 | `Update` |
| `BlastGameController.Stage` | 候选入槽、合成与落位收口 | `TryApplyStageCellClick` / `FinalizePlacement` |
| `BlastGameController.State` | 胜负、续命、中途退出 | `EnterLoseState` / `EvaluateContinueState` |
| `BlastGameController.PowerUps` | 锤子、法杖、魔法盒、回滚 | `TryUseHammer` / `TryUseWand` |
| `BlastGameController.ReplayHost` | Playback 与 Controller 的适配 | `TryDispatchReplayAction` |
| `BlastGameLevelSession` | 关卡路径、初始状态、队列和难度装配 | `LoadLevel` |
| `BlastLevelEntry` | 进关、跳关、失败重试 | `TransitionLevel` |
| `BlastGameViewPresenter` | 三区与 HUD 刷新编排 | `RefreshRuntimeViews` |
| `BlastGameReplayRuntime` | 回放录制、读档和会话 | `BeginFromFile` / `RecordGameplayAction` |

完整 Runtime 类职责见 [`game-main-runtime.md`](game-main-runtime.md)。

## Sim / Level / UI 入口（摘要）

| 主题 | 入口 | 细分索引 | 专题 |
|---|---|---|---|
| 战斗与攻击 | `BlastGameLogic.TickCombat` / `BlastAttackSystem` | [`game-main-sim.md`](game-main-sim.md) | [`Gameplay_Rules_Logic.md`](../Gameplay_Rules_Logic.md) |
| 放置与合成 | `BlastPlacementFlowState` / `BlastStageController` | [`game-main-sim.md`](game-main-sim.md) | [`Gameplay_Rules_Logic.md`](../Gameplay_Rules_Logic.md) |
| 下落与补块 | `BlastEngine.SimulateDropAndRefill` | [`game-main-sim.md`](game-main-sim.md) | [`Gameplay_Rules_Logic.md`](../Gameplay_Rules_Logic.md) |
| 关卡初始化 | `BlastLevelLoader.BuildInitialState` | [`game-main-level-core.md`](game-main-level-core.md) | [`Level_Entry_Init_Logic.md`](../Level_Entry_Init_Logic.md) |
| Board / Stage / Slots | `BlastGameViewPresenter.RefreshRuntimeViews` | [`game-main-ui.md`](game-main-ui.md) | [`GM_Board_Stage_Flow.md`](../GM_Board_Stage_Flow.md) |
| 回放 | `BlastGameReplayRuntime` / `BlastGameReplayPlayback` | [`game-main-runtime.md`](game-main-runtime.md) | [`Blast_Replay.md`](../Blast_Replay.md) |

## 快速定位

| 关键词 | 首选入口 | 细分页 |
|---|---|---|
| 进关、加载、重试 | `BlastLevelEntry` → `BlastGameLevelSession` → `Loading` | runtime / level-core |
| 主循环、战斗 tick | `Gameplay` → `BlastGameLogic.TickCombat` | runtime / sim |
| Stage 点击、入槽、合成 | `Stage` → `BlastPlacementFlowCoordinator` | runtime / sim |
| 失败、续命、退出 | `BlastGameController.State` | runtime |
| 道具 | `BlastGameController.PowerUps` | runtime |
| 回放 | `ReplayRuntime` → `Playback` → `ReplayHost` | runtime |
| Board / Stage 视图 | `BlastGameViewPresenter` | ui |

类职责细节只在细分页维护；规则口径进专题，不要在本页展开。
