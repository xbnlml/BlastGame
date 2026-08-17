# Editor 模块代码导航

## 用途

从“Bot 批跑、Workbench、关卡工具、Editor 菜单、构建工具”类提示词定位入口。本文只保留入口，不展开算法实现。

| 关键词 | 首选入口 | 相关文档 |
|---|---|---|
| Bot 单局 / 批跑 | `BlastBotService` / `BlastBotRangeRunner` | `Doc/Bot/Bot_Architecture.md` |
| Bot 评分 | `Assets/GameModule/Editor/Bot/Scoring/` | `Doc/Bot/Bot_Architecture.md` |
| Bot 对象池 | `BlastBotClonePool` | `Doc/Bot/Bot_Architecture.md` |
| 优化器 | `BlastOptimizerService` | `Doc/Bot/bot_optimization.md` |
| 关卡编辑 / 导入 | `Assets/GameModule/Editor/` 对应 Window | 通过菜单名搜索 |
| Game Model 生成 | `GameModelScaffoldWindow` | `Game_Model_Logic.md` |
| Prefab → View/Binder 脚本生成 | `PrefabUIViewGeneratorMenu` / `PrefabUIBinderGeneratorMenu` | `Doc/Tools/UIManager_Usage.md` |
| UI Sprite / 图集拆分与规范检查 | `SplitAtlasesWindow` | `Doc/Tools/SplitAtlases_Usage.md` |
| Jenkins / 打包 | `Tools/Python/buildpackage/` | `Doc/BuildPackage/Buildpackage_Mobile_Orchestrator.md` |
| 诊断检查 | `BlastCheckTool.py` | `Doc/MainGame/Game_Analysis_Logic.md` |

## 模块边界

- Editor 负责调度、配置、批跑和输出。
- 玩法规则归 `GameMain/Script/Sim/`，不在 Editor 复制。
- Bot 需要与 Runtime 对齐时，先看 `Bot_Runtime_Slot_State_Parity.md`。
- 工具输出用于诊断，不自动成为业务规则。

## 快速定位

- 看到 `BlastBot*.cs`：进入 `Doc/Bot/Bot_Architecture.md`。
- 看到 `BlastOptimizer*.cs`：进入 `Doc/Bot/bot_optimization.md`。
- 看到 `Jenkins*.sh` / `Jenkins*.py`：进入 BuildPackage 文档。
- 看到 Editor Window 名称：在 `Assets/GameModule/Editor/` 搜索类名。

不在本文维护完整类清单；代码入口变化时只更新本表对应行。

## 入口类职责（恢复）

| 类名 | 适用场景（简注） | 路径 |
|---|---|---|
| `PrefabUIScriptGeneratorCore` | Prefab→脚本生成共享核心（路径解析 / CollectBindings / 模板） | `Assets/Editor/PrefabUIScriptGeneratorCore.cs` |
| `PrefabUIViewGeneratorMenu` | 菜单：同时生成 View + Binder | `Assets/Editor/PrefabUIViewGeneratorMenu.cs` |
| `PrefabUIBinderGeneratorMenu` | 菜单：仅生成 / 覆盖 Binder（不改 View） | `Assets/Editor/PrefabUIBinderGeneratorMenu.cs` |
| `RepoSubmoduleBootstrap` | Unity 启动时配置 Git hooks，并在子模块缺失或未处于 `.gitmodules` 指定分支时同步 | `Assets/Editor/RepoSubmoduleBootstrap.cs` |
| `UITextPrefabScannerWindow` | UI Toolkit 扫描/导出 UIText；可保存/清空编辑器语言预览，实时刷新已加载 UIText、Inspector 文本及动态文字材质；界面日志可直接打开并定位 UIText | `Assets/GameModule/Editor/UITextPrefabScannerWindow.cs` |
| `UITextPrefabScannerWindow` | 扫描 `Assets/GameModule` 下 Prefab 的 `UIText`，导出预设、节点路径和文字 CSV | `Assets/GameModule/Editor/UITextPrefabScannerWindow.cs` |
| `SplitAtlasesWindow` | 按 Prefab 引用整理 UI Sprite、检查图集归属及增量规范 | `Assets/GameModule/Editor/SplitAtlasesWindow.cs` |
| `BlastBotAutoBatchTrigger` | 自动批跑触发入口 | `Assets/GameModule/Editor/Bot/BlastBotAutoBatchTrigger.cs` |
| `BlastBotBatchRunner` | Bot 批量运行编排入口 | `Assets/GameModule/Editor/Bot/BlastBotBatchRunner.cs` |
| `BlastBotCampaignRunner` | 战役多关卡批跑编排入口 | `Assets/GameModule/Editor/Bot/BlastBotCampaignRunner.cs` |
| `BlastWorkbenchWindow`（Bot partial） | Workbench 区间批跑 SO / 任务根目录 / 打开导出（`RunBotRangeFromScriptableObject`、`EnsureBotBatchTaskRootDir`、`OpenLastBotCsv`） | `Assets/GameModule/Editor/BlastWorkbenchWindow.Bot.cs` |
| `BlastBotRangeRunner` | 指定关卡范围跑批与导出；关卡 SO 加载与任务目录 `level-assets` 快照拷贝 | `Assets/GameModule/Editor/BlastBotRangeRunner.cs` / `.CampaignExport.cs` |
| `BlastOptimizerService` | 参数优化主入口 | `Assets/GameModule/Editor/Bot/BlastOptimizerService.cs` |
| `BlastH5OptimizerExport` | H5 风格结果导出入口 | `Assets/GameModule/Editor/Bot/BlastH5OptimizerExport.cs` |
| `BlastBotExportPathConfig` | 导出目录与命名规则配置（含任务根 `level-assets` 快照路径） | `Assets/GameModule/Editor/Bot/BlastBotExportPathConfig.cs` |
| `BlastBotHumanConfig` | Bot 人类化参数配置资产 | `Assets/GameModule/Editor/Bot/BlastBotHumanConfig.cs` |
| `BlastBotScorerVg` | Bot beam 节点评分统一入口 | `Assets/GameModule/Editor/Bot/Scoring/Vg/BlastBotScorerVg.cs` |

## Bot 详细索引（迁移自旧总文档）

## Editor/Bot（机器人批跑与优化）

### 总体定位

- 目录：`Assets/GameModule/Editor/Bot/`
- 角色：Editor 侧 Bot 仿真、策略评估、多档位参数优化（Workbench）、结果导出（不承担 Runtime UI 渲染）。

### 关键类型

- `BlastBotService`（`partial static`）
  - 角色：Bot 仿真主服务，负责单局/批量执行、动作选择策略、人类窗口模型、对拍诊断输出。
  - 关键入口：
    - `RunSingle`：单次仿真
    - `RunBatch`：批量仿真
    - `BuildInitialSimulationTemplate`：构建可复用初始状态模板
    - `ToBotLevelData(LevelProfileConfig)`：Phase 2 入口收敛的统一 DTO 适配点
  - 关键内部能力（用于后续读码定位）：
    - 选列策略：`ChooseAction` → `ChooseActionBeamGreedyCore`（`BlastBotService.Decision.cs`，评分经 `BlastBotScorerVg`）
    - 人类窗口推进：`EstimateLongestActionWindowMs`、`AdvanceCombatLikeH5`
    - 攻击系统状态恢复：beam/lookahead/temporal probe 通过 `SlotRowSweepSnapshot`、special focus 与 normal attack queue snapshot 恢复到克隆棋盘。
    - 失败诊断：`CaptureFailDecision`、`BuildFailDecisionContext`
  - partial 拆分（读码定位）：
    - `BlastBotService.Decision.cs`：beam search 与策略分支
    - `Editor/Bot/Scoring/`：评分子模块（见 `Vg/BlastBotScorerVg` 与各 `BlastBotScoring.*.cs`）
    - `Pool/BlastBotClonePool.cs`：ThreadLocal 对象池与 Clone
    - `BlastBotService.Simulation.cs` / `SimulationTail.cs`：战斗推进、预筛选编排、结算、队列填充

- `BlastBotScorerVg`（`static`，`Editor/Bot/Scoring/Vg/`）
  - 角色：Bot 评分对外唯一入口；各策略节点分组合一真源。
  - 关键方法：`EvaluateGreedy` / `EvaluateGreedyDeep`（`Scoring/Vg/BlastBotScorerVg.cs`）

- `BlastBotScoringContext`（`readonly struct`，同目录）
  - 角色：单次 beam 节点评分输入打包。
  - 同文件类型：`SearchNodeState`、`VisibleBalancedProfile`。

- `BlastBotScoring.*` / `Pool/BlastBotClonePool.cs`（均为 `partial BlastBotService`）
  - `Penalties` / `Demand` / `Snapshot` / `Pressure` / `Special` / `Filters` / `Link` / `Shared`：评分计算（`Scoring/` 下各文件 ≤ 400 行）。
  - `BlastBotClonePool.cs`：对象池、`CloneState`、`Rent*`/`Return*`（无 score 计算）。
- `BlastBotService.Editor`
  - 角色：Editor 绑定层（配置读取与注入）。
  - 关键方法：`EnsureEditorBindings`、`LoadHumanConfigFromAsset`、`CacheHumanConfigValues`（主线程一次性读取 `BlastBotHumanConfig` 并缓存到 `BlastBotService` 基础字段）。

- `BlastBotService.Campaign`
  - 角色：Bot 战役改造中的 partial 承载层，封装 campaign/score tracker 相关 helper，控制 `BlastBotService` 主文件体积。
  - 关键能力：score tracker 的“命中计分 + 时间轴累计”接入点（`RegisterAttackTick`）。

- `BlastBotReplayExport`（`static`）
  - 角色：Bot 回放协议适配层，把单局 Bot 结果组织成 Runtime 可消费的 replay 记录并落盘。
  - 关键方法：`BuildReplayRecords`、`ExportCampaignAttemptReplay`。

- `BlastBotExportPathConfig`（`internal static`）
  - 角色：Bot 导出目录、CSV/replay 文件名与时间格式等常量集中配置；replay session 与 `campaign-attempts.attemptIndex` 对齐（`BuildReplaySessionIdForAttempt`）。

- `BlastReplaySessionInfo`（Runtime 复用）
  - 角色：Bot 导出复用的 replay 会话元信息，不再维护 Bot 专用会话类。

- `BlastBotRunPolicy`（`static`）
  - 角色：统一 seed、runCount、并行批跑入口与难度上下文构建策略。
  - 关键方法：`BuildSeedBase`、`CreateSingleRunOptions`、`RunSingleBatchParallel`。

- `BlastOptimizerService`（`static`）
  - 角色：策略优化服务（含 GA 优化流程）。
  - 关键入口：`Optimize`
  - 关键内部能力：`EvaluateAcrossSeeds`、`Score`、`MutateIndividual`、`TournamentSelect`。

- `BlastH5OptimizerExport`（`partial static` + `.Editor`）
  - 角色：将优化/仿真结果组织为 H5 风格输出（JSON 与摘要行），用于对拍链路。
  - 关键方法：`WriteJsonFile`、`BuildH5StyleSummaryLines`。

- `BlastMultiTierTargetAdjuster`（`static`）
  - 角色：Multi-Tier 优化器的目标胜率调整器，基于 Phase1 胜率分布生成 configured/effective target 与 clamp 标记。
  - 关键方法：`BuildAdjustedTargets`。

- `BlastMultiTierOptimizer`
  - 角色：多档位优化（Phase0–3）；贝叶斯交叠晋级门 + P0/P3 公共最终池；构造时经 `BlastBotRangeRunner.TryCopyLevelProfileAssetToTaskDir` 把关卡 SO 快照到 telemetry `level-assets/`。
  - 快速定位：`CredibleIntervalOverlapGate` / `FinalHardGate` / `BuildFinalResultsFromCommonPool` / `MergeEvaluations` / `HasFailedTiers`；`summary.csv` 含 Status/SourcePhase/RawGap/OverlapGap。
  - 权重默认：`weightWinRate=0.70` / `weightFailDistribution=0.30`。

- `BlastWorkbenchWindow.MultiTierOpt` / `BlastMultiTierExcelConfigReader`
  - 角色：Workbench UI 与 Jenkins/批跑入口；失败时检查 `StoppedDueToInsufficientPhase1` 与 `HasFailedTiers`。
- `BlastBotHumanConfig`（`ScriptableObject`）
  - 角色：人类行为窗口参数配置资产（延迟采样、权重等）；`BlastBotService` 运行时仅通过集中读取入口消费，不再经 `BlastBotHumanSettings` 中间类。

- Bot 结果模型（在 `BlastBotService.RunModels.cs`）
  - `BlastBotRunResult`：单次运行结果（含 replay 导出记录与 session 信息）
  - `BlastBotBatchResult`：批量统计结果
  - `BlastBotRunOptions`：运行参数载体
- `BlastBotCampaignOptions / BlastBotCampaignAttemptResult / BlastBotCampaignStateSnapshot / BlastBotCampaignResult`：战役运行配置与输出 DTO（尝试级日志 + 状态快照 + 总结）。

- Bot Campaign 导出行模型（`Core/Bot/BlastBotExportRow.cs`）
  - `BlastBotExportAttemptRow`：`campaign-attempts*.csv` 单行 schema（`CsvHeader` / `ToCsvLine`）。
  - `BlastBotExportCampaignSummaryRow`：`campaign-summary*.csv` 按关聚合单行 schema（`CsvHeader` / `ToCsvLine`）；含 `startDifficulty` / `shuffleSplitCount` / `shuffleSplitRatios` / `shuffleOverflowFactor` 四参数。

- `BlastBotLocalCampaignState`
  - 角色：Bot 本地战役状态容器，保存 levelRecords/profile/currentLevel/cycle，并承接共享结算逻辑输入输出。

- `BlastBotCampaignRunner`
  - 角色：战役编排（同关同 seed 重试、胜后推进下一关、每次尝试输出快照）。
  - 关键入口：`RunCampaign`。

- `BlastBotRangeRunner`
  - 入口收敛：固定示例菜单（含 `Campaign示例跑法(1-3关)`）已移除，统一使用范围参数化入口（`RunLevelRangeAndExportExcel` / `RunCampaignAndExportExcel`），并仅保留 ScriptableObject 关卡来源。
  - 结构备注：campaign 导出与 replay 落盘逻辑已拆到 `BlastBotRangeRunner.CampaignExport.cs` partial。
