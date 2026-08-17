# GameMain Level / Core 索引

## 用途

从“进关初始化、关卡配置、初始状态、动态难度、共享纯逻辑”类提示词定位代码。

| 关键词 | 首选入口 | 专题 |
|---|---|---|
| 配置解析 | `BlastLevelConfigParser` | `Level_Entry_Init_Logic.md` |
| 初始盘面、槽位、候选 | `BlastLevelLoader` | `Level_Entry_Init_Logic.md` |
| 关卡会话初始化 | `BlastGameLevelSession` | `Level_Entry_Init_Logic.md` |
| 难度 Context | `BlastDifficultyContextFactory` | `Blast_DynamicDifficulty.md` |
| 动态难度公式 | `BlastDynamicDifficultyPureLogic` | `Blast_DynamicDifficulty.md` |
| 得分纯逻辑 | `BlastScorePureLogic` | `Game_Score_Logic.md` |
| 结算累计 | `BlastLevelSettlementPureLogic` | `Game_Score_Logic.md` |
| 共享数据 / DTO | `BlastTypes` | `Game_Model_Logic.md` |

## 初始化主链路

`LevelProfileConfig → Parser → LevelLoader → GameLevelSession → BlastGameState / Slots / Candidates → Controller`

## Level 类职责

| 类 / 文件 | 职责 | 协作者 |
|---|---|---|
| `BlastLevelConfigParser` | 关卡配置读取与解析 | LevelProfileConfig |
| `BlastLevelLoader` | 配置转运行态 State/Slots/Candidates | GameLevelSession / BlastTypes |
| `BlastGameLevelSession` | 进关会话门面（路径、队列、难度、runtime reset） | Loader / DifficultyContextFactory |

## Core 类职责

| 类 / 文件 | 职责 | 协作者 |
|---|---|---|
| `BlastDifficultyContextFactory` | 难度上下文唯一组装入口（`BuildForEntry`） | Runtime / Bot / Replay |
| `BlastDifficultyEntryRequest` | 进关难度路由 DTO | ContextFactory |
| `BlastDynamicDifficultyPureLogic` | 动态难度共享公式真源 | DifficultyManager |
| `BlastDynamicDifficultyManager` | 难度管理辅助 | PureLogic |
| `BlastScorePureLogic` | 计分/连击共享纯逻辑 | Runtime / Sim / Bot |
| `BlastLevelSettlementPureLogic` | 关后累计/结算共享逻辑 | Runtime / Bot |
| `BlastMergeSimContext` | Bot/Headless 合并门禁上下文 | TickCombat |
| `BlastPool2X2Resolver` | Pool 2x2 锚点解析 | LevelLoader |
| `Blast2X2OwnershipResolver` | 2x2 归属解析 | Engine / Attack |
| `BlastTypes` | 共享 State / Piece / Candidate / 配置 DTO | 全链路 |
| `BlastMath` | 数学辅助 | Core |
| `ResourcePathData` | 资源路径常量 | UI / Runtime |

## 代码目录

- `Assets/GameModule/GameMain/Script/Level/`
- `Assets/GameModule/GameMain/Script/Core/`
