# Skill 反向映射导航

- 范围：跨模块技能路由与关注文件映射。

## Skill 反向映射（9 个 skill → 关注文件/禁止越界）

> 用途：后续新建 skill 时直接按本表定义 scope，避免职责漂移。
> 约定：每个 skill 都应“只读/只改自己范围内的文件”；跨范围改动必须先由 orchestrator skill 派发。

### 1. game-module-orchestrator（GameMain 统筹）

- 定位：总入口，负责派发到下面 3 个子 skill（score / gameplay-flow / gameplay-rules）与 analysis。
- 关注目录：
  - `Assets/GameModule/GameMain/`
- 关注文件（入口）：
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.cs`（及同名 partial 分文件）
  - `Doc/MainGame/Blast_MainGame.md`
- 不直接承担的工作：
  - Bot 仿真（归 `game-bot-orchestrator`）
  - 打包流程（归 `buildpackage-mobile-orchestrator`）

### 2. game-score-logic（得分 / 连击 / 命中反馈）

- 关注文件：
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Gameplay.cs`
    - 重点方法：`ProcessAttackHitFeedback`、`RegisterHitCombos`、`RegisterHitComboBonus`、`RefreshLevelProgress`
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.AttackOnce.cs`
    - 重点方法：`SlotAttackOnce`、`GetHitData`
  - `Assets/GameModule/GameMain/Script/UI/ComboStarEffectView.cs`（连击推进提示）
  - `Assets/GameModule/GameMain/Script/UI/BlastHudView.cs`（得分与连击 HUD 显示）
- 文档：
  - `Doc/Blast_ScoreCombo_Notes.md`
- 不越界范围：
  - 不改特殊块规则（归 `gameplay-rules-logic`）
  - 不改关卡加载主流程（归 `gameplay-flow-logic`）

### 3. gameplay-flow-logic（玩法主流程）

- 关注文件：
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Loading.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Gameplay.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Stage.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.State.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Views.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.PowerUps.cs`
  - `Assets/GameModule/GameMain/Script/Level/BlastLevelLoader.cs`
  - `Assets/GameModule/GameMain/Script/Level/BlastLevelConfigParser.cs`
  - `Assets/GameModule/GameMain/Script/Level/LevelProfileConfigToBlastLevelData.cs`
- 文档：
  - `Doc/MainGame/Blast_MainGame.md`（主游戏/记录回放章节）
  - `Doc/BlastGameController_Reorg_And_Replay_Plan.md`
- 不越界范围：
  - 攻击系统内部与特殊块判定改动（归 `gameplay-rules-logic`）
  - Bot 仿真（归 `game-bot-orchestrator`）

### 4. gameplay-rules-logic（玩法规则：特殊块/队列/难度/下落）

- 关注文件：
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.Update.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.Targeting.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.AttackOnce.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.SpecialBlocks.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.State.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastAttackSystem.Parity.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastEngine.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastQueueBuilder.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastGameStateTargetUnits.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastDifficultyApplier.cs`
  - `Assets/GameModule/GameMain/Script/Sim/BlastDotNetRandom.cs`
- 文档：
  - `Doc/MainGame/Blast_MainGame.md`（主游戏/积分系统/配置章节）
  - `Doc/MainGame/POWERUP-SYSTEM-Unity.md`
  - `Doc/MainGame/GM_Board_Stage_Flow.md`
  - `Doc/MainGame/GM_Board_Stage_Flow.md`
- 不越界范围：
  - UI 表现（归 `game-score-logic` 中的 HUD 或主流程对应 View）
  - Bot 仿真逻辑（归 `game-bot-orchestrator`）

### 5. game-analysis-logic（分析 / 诊断 / 对拍）

- 关注输出与工具：
  - `BlastDifficultyApplier.AnalyzeQueueDifficulty`（难度对拍）
  - `Tools/Python/GameTools/BlastCheckTool.py`（读/校验工具；保持只读）
  - `Tools/Python/GameTools/BlastCheckTool.md`
  - `Doc/Tools/Tooling_Local_Notes.md`（调研工具沉淀）
- 文档：
  - `Doc/MainGame/Blast_MainGame.md`（主游戏与参考章节中的调试说明）
  - `Doc/AI/`（各次分析/对拍的过程记录）
- 不越界范围：
  - 不改玩法规则或主流程代码；仅输出/解读调试产物，必要修复提交给对应 skill。

### 6. game-bi-logic（玩法 BI 打点）

- 关注文件：
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameLevelPlayBIModels.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastActionReplayModels.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameReplayRuntime.cs`
  - `Assets/Betta/Scripts/Runtime/BI/BlastGameBI.cs`
- 文档：
  - `Doc/BI/Blast 打点字段说明（待补充版）.md`
  - `Doc/MainGame/Game_BI_Logic.md`
- 不越界范围：
  - 不把 replay record 当作业务打点模型复用。
  - 不改 Bot 批跑与打包链路。

### 7. game-bot-orchestrator（Bot 模块统筹）

- 关注目录：
  - `Assets/GameModule/Editor/Bot/`
- 关注文件：
  - `Assets/GameModule/Editor/Bot/BlastBotService.cs`
  - `Assets/GameModule/Editor/Bot/BlastBotService.Decision.cs`
  - `Assets/GameModule/Editor/Bot/Pool/BlastBotClonePool.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/Vg/BlastBotScorerVg.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoringContext.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Penalties.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Demand.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Snapshot.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Pressure.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Special.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Filters.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Link.cs`
  - `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Shared.cs`
  - `Assets/GameModule/Editor/Bot/BlastBotRunPolicy.cs`
  - `Assets/GameModule/Editor/Bot/BlastOptimizerService.cs`
  - `Assets/GameModule/Editor/Bot/BlastH5OptimizerExport.cs`
  - `Assets/GameModule/Editor/Bot/BlastH5OptimizerExport.Editor.cs`
  - `Assets/GameModule/Editor/Bot/BlastBotHumanConfig.cs`
  - `Assets/GameModule/Editor/BlastBotRangeRunner.cs`（批跑入口）
- 文档：
  - `Doc/Bot/Bot_Architecture.md`
  - `Doc/Bot/Bot_Execution_Logic_Unity.md`
  - `Doc/Bot/BlastBot_SpeedOptimization_Checklist.md`
  - `Doc/Bot/BlastBot_ParitySafe_Optimization_Plan.md`
  - `Doc/Bot/WorkbenchOptimizationFlow.md`
- 不越界范围：
  - 不直接修改 `GameMain/Script/Runtime|Sim|UI`；必须通过 orchestrator 派发给 gameplay/score/rules skill。

### 8. game-pass-logic（通行证）

- 关注目录：
  - `Assets/GameModule/GamePassModule/`
- 关注文件：
  - `Assets/GameModule/GamePassModule/Script/Model/GamePassModel.cs`
  - `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.State.cs`（胜利后直调加星）
  - `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelView.cs`
  - `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelPass.cs`
  - `Assets/GameModule/HomeModule/Script/RunTime/LevelPassData.cs`
- 文档：
  - `Doc/MainGame/Game_Pass_Logic.md`
  - `Doc/MainGame/Game_Model_Logic.md`
- 不越界范围：
  - 不在事件回调里承载通行证数据写入；数据更新必须走 `GamePassModel` 直调入口。

### 9. buildpackage-mobile-orchestrator（iOS / Android 打包）

- 触发口令：你说“打包流程”时默认走本 skill。
- 关注目录：
  - `Tools/Python/buildpackage/`
- 关注文件：
  - `Tools/Python/buildpackage/JenkinsProcess.py`
  - `Tools/Python/buildpackage/JenkinsNotifyDingTalk.py`
  - `Tools/Python/buildpackage/JenkinsRecorder.py`
  - `Tools/Python/buildpackage/JenkinsUtils.py`
  - `Tools/Python/buildpackage/GenerateQRCode.py`
  - `Tools/Python/buildpackage/SimpleHTTPServer.py`
- 可读的版本来源（只读）：
  - `ProjectSettings/ProjectSettings.asset`（`bundleVersion` / `AndroidBundleVersionCode` / `PlayerSettings/buildNumber/iPhone`）
  - `Assets/Betta/Res/Info/ClientInfo.json`（`ClientBuild`）
- 文档：
  - `Doc/AI/2026-04-21-jenkins-app-version-workspace-file.md`
- 不越界范围：
  - 不改游戏逻辑、Bot 代码、关卡配置；仅负责打包/分发/通知链路与相关脚本。
