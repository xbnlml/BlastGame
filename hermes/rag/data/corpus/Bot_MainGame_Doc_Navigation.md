# Bot & MainGame 文档导航

本页用于统一导航 `Doc/Bot` 与 `Doc/MainGame` 的当前有效文档入口，避免回到历史方案文档。

## Bot 文档入口

- 主架构与当前规则：`Doc/Bot/Bot_Architecture.md`
- Bot 与 Runtime 槽位状态驱动/使用对照（专题，状态口径真源）：`Doc/Bot/Bot_Runtime_Slot_State_Parity.md`
- Bot 批跑无损提速说明：`Doc/Bot/Bot_Architecture.md` §4.7
- Unity 执行链路说明：`Doc/Bot/Bot_Execution_Logic_Unity.md`
- 性能优化检查清单：`Doc/Bot/BlastBot_SpeedOptimization_Checklist.md`
- Workbench 优化流程：`Doc/Bot/WorkbenchOptimizationFlow.md`

## MainGame 文档入口

- 主导航（模块索引）：`Doc/MainGame/Blast_MainGame.md`
- 查代码总则：`AGENTS.md`
- 主流程模块：`Doc/MainGame/Gameplay_Flow_Logic.md`
- 场景与壳层 UI：`Doc/MainGame/Scene_And_UI_Transition.md`
- UI 框架（Betta + Blast 窗口）：`Doc/Tools/UIManager_Usage.md`
- 玩法规则模块：`Doc/MainGame/Gameplay_Rules_Logic.md`
- 得分模块：`Doc/MainGame/Game_Score_Logic.md`
- 分析模块：`Doc/MainGame/Game_Analysis_Logic.md`
- 关卡初始化模块：`Doc/MainGame/Level_Entry_Init_Logic.md`
- Common 运行时基础设施：`Doc/MainGame/Common_Runtime_Infrastructure.md`
- 玩家数据模块（UserModule）：`Doc/MainGame/Player_Data_Logic.md`
- 服务器关卡数据模块（UserModule）：`Playbooks/server-level-data-logic.md`
- 回放专题：`Doc/MainGame/Blast_Replay.md`
- 动态难度专题：`Doc/MainGame/Blast_DynamicDifficulty.md`
- 棋盘与 Stage 流程：`Doc/MainGame/GM_Board_Stage_Flow.md`
- 道具专题：`Doc/MainGame/POWERUP-SYSTEM-Unity.md`
- 动态难度前端需求参考：`Doc/MainGame/DynamicDifficulty_FE_Requirement.md`

## GuideModule 文档入口

- 引导系统实现文档：`Doc/GuideModule/GuideModule_Implementation.md`
- 配置源：`Assets/Module/Guide_Scenario/Config/Data/guide_scenario.json`
- 代码模块：`Assets/GameModule/GuideModule/`

## 类功能定位入口

- MainGame 全量类职责总纲：`Doc/MainGame/gamemain-class-function-index.md`
- MainGame 细分类索引：`Doc/MainGame/module-index/game-main-agent-index.md`
- 模块文档模板：`Doc/MainGame/Class_Function_Location_Template.md`
- 按模块查询：先看 MainGame 总纲，再进细分页；如果目标模块文档里还有“类功能定位”小节，就把它当作补充入口，不再当作唯一默认入口。

## 工具与本地集成

- Telegram 遥控本机 Cursor Agent（cc-connect 版）：`Doc/Tools/telegram-cursor-local-integration.md`
- 本地工具命令与 Editor 约定：`Doc/Tools/Tooling_Local_Notes.md`

## 使用建议

- 先看主手册（Bot 看 `Bot_Architecture`，MainGame 看 `Blast_MainGame`），再按专题下钻。
- 需要快速定位代码时：遵循 `AGENTS.md`，再按模块文档和类功能索引补充上下文。
- 若新增专题文档，请同步更新本页，保持入口稳定。
- Bot Runtime 对齐问题：先看 `Bot_Runtime_Slot_State_Parity.md`，再按其中的代码锚点进入 Runtime/Sim 实现。
