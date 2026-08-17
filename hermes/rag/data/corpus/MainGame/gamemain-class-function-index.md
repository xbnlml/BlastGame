# GameModule 类职责总纲

## 用途

这是 `Assets/GameModule/` 的模块级代码导航。它只回答“模块和核心类负责什么、下一步看哪里”，不承载实现细节。

## 导航顺序

```text
关键词 / 文件名
  → 本页模块
  → 模块 index
  → 类职责
  → 主流程专题
  → C# 代码
```

不确定关键词时，先看 [`keyword-map.md`](module-index/keyword-map.md)。

## 模块总览

| 模块 | 目录 | 核心职责 | 首选入口 | 专题 / 索引 |
|---|---|---|---|---|
| GameMain | `Assets/GameModule/GameMain/` | 局内主流程、规则、关卡、视图 | `BlastGameController` | [`game-main.md`](module-index/game-main.md) |
| Common | `Assets/GameModule/Common/` | 模型注册、资源、定时、弹板、场景和公共 UI | `GameModelManager` / `ResourcesManager` | [`common.md`](module-index/common.md) |
| GamePassModule | `Assets/GameModule/GamePassModule/` | 通行证赛季、星星、奖励 | `GamePassModel` | [`game-pass-module.md`](module-index/game-pass-module.md) |
| DailyDeliveryModule | `Assets/GameModule/DailyDeliveryModule/` | 14 天循环签到和领奖 | `DailyDeliveryModel` | [`daily-delivery-module.md`](module-index/daily-delivery-module.md) |
| GrandOpeningWeekModule | `Assets/GameModule/GrandOpeningWeekModule/` | 新手 7 天签到和终点奖励 | `GrandOpeningWeekModel` | [`grand-opening-week-module.md`](module-index/grand-opening-week-module.md) |
| UserModule | `Assets/GameModule/UserModule/` | 玩家 Profile、体力、金币、等级、道具 | `UserModuleManager` | [`user-module.md`](module-index/user-module.md) |
| HomeModule | `Assets/GameModule/HomeModule/` | 大厅、Top、Profile、设置和活动入口 | `TopUIView` / `UIHomeLevelView` | [`home-module.md`](module-index/home-module.md) |
| GuideModule | `Assets/GameModule/GuideModule/` | 引导配置、运行时和 UI | `GuideScenarioManager` / `GuideScenarioSession` | [`guide-module.md`](module-index/guide-module.md) |

## GameMain 核心职责

### Runtime / 流程

| 类 / 文件 | 一句话职责 | 关键词 | 下一步 |
|---|---|---|---|
| `BlastGameController` | 固定时间步协调局内 State、Sim、视图、道具和结束状态 | 主流程、主循环 | [`Gameplay_Flow_Logic.md`](Gameplay_Flow_Logic.md) |
| `BlastGameLevelSession` | 将关卡配置装配为 State、Slots、Candidates、Queue 和 DifficultyContext | 进关、初始化 | [`Level_Entry_Init_Logic.md`](Level_Entry_Init_Logic.md) |
| `BlastLevelEntry` | 统一进关、跳关和失败重试入口 | 进关、重试 | [`Level_Entry_Init_Logic.md`](Level_Entry_Init_Logic.md) |
| `BlastCombatBridge` | Controller 与 AttackSystem 之间的战斗槽缓冲 | 攻击槽、战斗 | [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md) |
| `BlastPlacementFlowCoordinator` | 管理 Stage → Slot 放置流的暂态和时序 | 放置流、门控 | [`GM_Board_Stage_Flow.md`](GM_Board_Stage_Flow.md) |
| `BlastRuntimeConfig` | 提供 Runtime 使用的 DataConfig、UIConfig 和金币入口 | 配置、金币 | [`Gameplay_Flow_Logic.md`](Gameplay_Flow_Logic.md) |
| `BlastGameViewPresenter` | 将 Runtime 数据变化分发到 Board、Stage、Slots、Effects 和 HUD | 视图刷新 | [`GM_Board_Stage_Flow.md`](GM_Board_Stage_Flow.md) |
| `BlastGameReplayRuntime` | 统一回放录制、读档、会话和进度入口 | 回放、录制 | [`Blast_Replay.md`](Blast_Replay.md) |
| `BlastGameReplayPlayback` | 推进回放游标、等待、动作派发和结束 | 回放播放 | [`Blast_Replay.md`](Blast_Replay.md) |

### Sim / Level / Core

| 类 / 文件 | 一句话职责 | 关键词 | 下一步 |
|---|---|---|---|
| `BlastGameLogic` | 共享 Runtime/Bot/Replay 的战斗 tick | TickCombat、战斗 | [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md) |
| `BlastAttackSystem` | 攻击冷却、目标选择、命中和攻击状态 | 攻击、目标 | [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md) |
| `BlastEngine` | 盘面下落、补块和特殊结构 settle | 下落、补块 | [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md) |
| `BlastStageController` | 候选点击、可放置判断和槽位合成规划 | Stage、合成 | [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md) |
| `BlastPlacementFlowState` | 放置流的纯数据状态机 | 放置状态 | [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md) |
| `BlastQueueBuilder` | 构建原始队列、难度队列和初始资源 | 队列、Pool | [`Gameplay_Rules_Logic.md`](Gameplay_Rules_Logic.md) |
| `BlastDifficultyContextFactory` | 统一组装各入口使用的动态难度上下文 | 动态难度 | [`Blast_DynamicDifficulty.md`](Blast_DynamicDifficulty.md) |
| `BlastScorePureLogic` | 共享计分、连击和星级计算 | 得分、连击 | [`Game_Score_Logic.md`](Game_Score_Logic.md) |
| `BlastTypes` | 定义 GameMain 的核心 State、Piece、Candidate 和配置数据 | 数据模型 | [`Game_Model_Logic.md`](Game_Model_Logic.md) |

### Board / Stage / Slots

| 类 / 文件 | 一句话职责 | 关键词 | 下一步 |
|---|---|---|---|
| `BlastBoardView` | 展示盘面状态并管理 Board Cell 生命周期 | Board、刷新 | [`GM_Board_Flow.md`](GM_Board_Flow.md) |
| `BlastStageView` | 展示候选并接收 Stage 视觉更新 | Stage、候选 | [`GM_Board_Stage_Flow.md`](GM_Board_Stage_Flow.md) |
| `BlastSlotsView` | 展示正式/临时槽位并同步槽位状态 | Slots、槽位 | [`GM_Board_Stage_Flow.md`](GM_Board_Stage_Flow.md) |
| `BlastStageAnimalView` | 承载 Stage/Slot 共用的动物视觉实例 | 动物、飞行 | [`Stage_Animal_Animation_Playback.md`](Stage_Animal_Animation_Playback.md) |
| `BlastStageAnimalPool` | 管理动物视觉对象的出池、复用和回收 | 对象池 | [`Stage_Animal_Animation_Playback.md`](Stage_Animal_Animation_Playback.md) |

## Common 核心职责

| 类 | 一句话职责 | 关键词 |
|---|---|---|
| `GameModelManager` | 注册、初始化和按活动类型路由 Model | Model、活动 |
| `ResourcesManager` | 统一资源加载、缓存和卸载 | 资源 |
| `TimerManager` | 提供全局延时、倒计时和跨天触发 | 定时、跨天 |
| `PopUpManager` | 按触发时机编排弹板队列 | 弹板 |
| `GameSceneSwitchCoordinator` | 统一场景切换、遮罩和异步加载 | 场景 |
| `ReturnToLobbyFlowManager` | 编排返回大厅和清理流程 | 回大厅 |
| `AnimatorManager` | 统一 Spine、Animator、Timeline 播放和清理 | 动画 |

详情：[`common.md`](module-index/common.md) / [`Common_Runtime_Infrastructure.md`](Common_Runtime_Infrastructure.md)。

## 系统功能模块

| 模块 | 核心类 | 一句话职责 | 下一步 |
|---|---|---|---|
| GamePass | `GamePassModel` | 管理赛季、星星、免费/付费和循环奖励资格 | [`game-pass-module.md`](module-index/game-pass-module.md) |
| Daily Delivery | `DailyDeliveryModel` | 管理 14 天循环签到、里程碑和补签 | [`daily-delivery-module.md`](module-index/daily-delivery-module.md) |
| Grand Opening Week | `GrandOpeningWeekModel` | 管理新手 7 天签到和终点大奖 | [`grand-opening-week-module.md`](module-index/grand-opening-week-module.md) |
| User | `UserModuleManager` | 管理 Profile、体力、金币、等级和道具入口 | [`user-module.md`](module-index/user-module.md) |
| Home | `TopUIView` / `UIHomeLevelView` | 承载大厅展示、设置、Profile 和活动入口 | [`home-module.md`](module-index/home-module.md) |
| Guide | `GuideScenarioManager` / `GuideScenarioSession` | 根据配置推进剧情、打字和手势引导 | [`guide-module.md`](module-index/guide-module.md) |

## Bot / Editor

| 类 | 一句话职责 | 关键词 | 下一步 |
|---|---|---|---|
| `BlastBotService` | 执行 Bot 单局和策略推进 | Bot、单局 | [`Bot_Architecture.md`](../Bot/Bot_Architecture.md) |
| `BlastBotScorerVg` | 对候选状态进行评分 | Bot、评分 | [`Bot_Architecture.md`](../Bot/Bot_Architecture.md) |
| `BlastBotClonePool` | 复用搜索分支的状态对象 | Bot、对象池 | [`Bot_Architecture.md`](../Bot/Bot_Architecture.md) |
| `BlastOptimizerService` | 驱动参数搜索和优化批次 | 优化器 | [`bot_optimization.md`](../Bot/bot_optimization.md) |
| `BlastBotRangeRunner` | 执行关卡区间批跑和结果汇总 | 批跑 | [`Bot_Execution_Logic_Unity.md`](../Bot/Bot_Execution_Logic_Unity.md) |

## 维护规则

- 本页只保留模块和核心类职责，不复制方法清单。
- 类职责以当前代码和 CodeGraph 为准；Git 删除记录只用于补充缺失摘要。
- 新增核心类时补一行职责和关键词，并链接到对应专题。
- 旧计划、历史日志、动画参数和字段百科不进入本页。
