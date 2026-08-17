# GameMain Runtime / 流程索引

## 用途

从“进关、主循环、道具、胜负、回放、BI”类提示词定位 Runtime 入口与类职责。

## 主入口

| 关键词 | 首选类 / 文件 | 下一步 |
|---|---|---|
| 主流程、主循环 | `BlastGameController` / `Gameplay` | `Gameplay_Flow_Logic.md` |
| 进关、加载、重试 | `BlastLevelEntry` / `BlastGameLevelSession` / `Loading` | `Level_Entry_Init_Logic.md` |
| Stage 入槽、放置流 | `PlacementFlow` / `BlastPlacementFlowCoordinator` | `Gameplay_Rules_Logic.md` |
| 攻击槽、战斗桥接 | `Combat` / `BlastCombatBridge` | `Gameplay_Rules_Logic.md` |
| 失败、续命、退出 | `BlastGameController.State` | `Gameplay_Flow_Logic.md` |
| FailOffer / Play On Offer | `FailOfferModel` / `UIGameContinueView` | `PlayOn_Offer_Logic.md` |
| 锤子、法杖、魔法盒 | `BlastGameController.PowerUps` / `BlastPowerUpHammer` / `BlastPowerUpWand` / `BlastWandShuffleAnim` | `POWERUP-SYSTEM-Unity.md` |
| 回放录制、播放 | `BlastGameReplayRuntime` / `Playback` / `ReplayHost` | `Blast_Replay.md` |
| 视图编排 | `BlastGameViewPresenter` | `GM_Board_Stage_Flow.md` |
| BI | `BlastGameLevelPlayBIReporter` | `Game_BI_Logic.md` |

## 主流程顺序

`LevelEntry → Loading / LevelSession → Controller.FixedUpdate / Update → Sim Tick → Presenter Refresh → Win / Lose / Replay`

## 核心类职责

| 类 / 文件 | 职责 | 协作者 |
|---|---|---|
| `BlastGameController` | 运行时总编排：加载、主循环、放置流门控、胜负、道具、回放宿主 | LevelSession / Presenter / StageController / ReplayRuntime |
| `BlastGameRuntimeData` | 逻辑帧与累计毫秒等最小运行态数据 | Controller |
| `BlastGameLevelSession` | 关卡路径、State/Slots/Candidates、队列与难度装配 | LevelLoader / DifficultyContextFactory |
| `BlastLevelEntry` | 进关、跳关、失败重试统一入口；重试体力不足→`UIHealthView` | Controller.LevelEntry / LevelSession |
| `BlastGameViewPresenter` | Board/Stage/Slots/Effects/HUD 刷新；运行期只消费 dirty/delta | 三区 View / EffectLayerController |
| `BlastCombatBridge` | AttackSystem 与战斗槽缓冲桥接 | AttackSystem / Controller.Combat |
| `BlastPlacementFlowCoordinator` | Stage→Slot 放置流状态与 stage-load frame | PlacementFlowState / StageController |
| `BlastRuntimeConfig` | DataConfig / UIConfig / 金币入口 | Controller.Config |
| `BlastStageController` | 可放置判断、入槽与槽位合成规划 | Controller.Stage / Sim |
| `BlastGameRollbackRuntime` | 回退快照深拷贝真源；恢复须再次 Clone | Controller.PowerUps |
| `BlastPowerUpWand` | 魔棒洗牌算法（完整 feature 置换、link pair 不拆）+ from→to 映射 | Controller.PowerUps |
| `BlastWandShuffleAnim` | 魔棒换位直线调度（统一用时） | StageView / Controller.PowerUps |
| `BlastHammerAbsorbBlockFly` | 锤子逐块吸收起飞调度（row/col 升序 + 间隔衰减） | Controller.PowerUps / GuideFake |
| `BlastStageView` | 魔棒换位的 view 置换校验、内容优先落定与 Prop2 行距 tween | Controller.PowerUps / ViewPresenter |
| `BlastGameReplayRuntime` | 录制、读档、会话与进度门面 | Playback / RecordAdapter / RuntimeAdapter |
| `BlastGameReplayPlayback` | Step、等待/快进、游标与结束调度 | ReplayHost / FlowCoordinator |
| `BlastReplayFlowData` | 回放流程状态容器 | FlowCoordinator |
| `BlastReplayFlowCoordinator` | 回放推进决策（不直接 UI/IO） | Playback / RuntimeAdapter |
| `BlastReplayRuntimeAdapter` | envelope/文件读取与会话副作用 | ReplayRuntime |
| `BlastReplayRecordAdapter` | 录制写入与 action kind 映射 | ReplayRuntime |
| `BlastGameLevelPlayBIReporter` | 玩法 BI 上报单点 | BIModels |

## Controller partial 职责

| Partial | 职责 |
|---|---|
| `Loading` | `LoadLevel` facade；装配下沉到 LevelSession；回放 `load_level` 记录 |
| `Gameplay` | Update、命中反馈、连击、key-lock、回放推进钩子 |
| `Stage` | 候选入槽、推进与槽位交互收口 |
| `Views` | 经 Presenter 投递三区/Effects/HUD 刷新 |
| `State` | 胜负、续命、中途退出 |
| `PowerUps` | 道具 facade；rollback 复用 RollbackRuntime |
| `Combat` / `PlacementFlow` | 攻击槽缓冲；放置流门控 |
| `ReplayHost` / `Dispatch` / `Placement` / `PowerUps` / `Difficulty` | 回放宿主与动作落地适配 |

## 放置流门控要点

- `AttackReady/Complete` 由 `FixedUpdate` 定时消费，不由放置动画回调释放。
- Stage 同帧节流按列 `_lastStageLoadFrameByCol`；解锁时长走 `BlastPlacementFlowTiming`。

## 代码路径

`Assets/GameModule/GameMain/Script/Runtime/BlastGameController*.cs`、`BlastGameLevelSession.cs`、`BlastLevelEntry.cs`、`BlastGameReplay*.cs`、`BlastCombatBridge.cs`、`BlastPlacementFlowCoordinator.cs`、`BlastRuntimeConfig.cs`
