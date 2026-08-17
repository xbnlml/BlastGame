# GameMain 多 Agent 总览

- 模块目录：`Assets/GameModule/GameMain/`
- 作用：第一步只选层，不急着进具体类。
- 细分入口：
  - [Runtime / 流程](game-main-runtime.md)
  - [Sim / 规则](game-main-sim.md)
  - [Level / Core](game-main-level-core.md)
  - [UI / 视图](game-main-ui.md)

## 先怎么分

| 层级 | 适合先看什么 | 对应专题文档 |
|---|---|---|
| Runtime / 流程 | 入口编排、回放、道具、BI、视图桥接 | [`Gameplay_Flow_Logic.md`](../Gameplay_Flow_Logic.md) / [`Blast_Replay.md`](../Blast_Replay.md) / [`Game_BI_Logic.md`](../Game_BI_Logic.md) / [`Game_Analysis_Logic.md`](../Game_Analysis_Logic.md) / [`Level_Entry_Init_Logic.md`](../Level_Entry_Init_Logic.md) |
| Sim / 规则 | 战斗、放置、队列、下落、补块、得分 | [`Gameplay_Rules_Logic.md`](../Gameplay_Rules_Logic.md) / [`Game_Score_Logic.md`](../Game_Score_Logic.md) / [`Blast_DynamicDifficulty.md`](../Blast_DynamicDifficulty.md) |
| Level / Core | 关卡加载、初始状态、纯逻辑、DTO | [`Level_Entry_Init_Logic.md`](../Level_Entry_Init_Logic.md) / [`Game_Model_Logic.md`](../Game_Model_Logic.md) / [`Common_Runtime_Infrastructure.md`](../Common_Runtime_Infrastructure.md) |
| UI / 视图 | 视图绑定、状态机、动画、对象池 | [`GM_Board_Stage_Flow.md`](../GM_Board_Stage_Flow.md) / [`Stage_Animal_Animation_Playback.md`](../Stage_Animal_Animation_Playback.md) / [`POWERUP-SYSTEM-Unity.md`](../POWERUP-SYSTEM-Unity.md) / [`Scene_And_UI_Transition.md`](../Scene_And_UI_Transition.md) |

## 使用顺序

1. 先从上表选层。
2. 再进对应细分页找类名、文件、方法锚点。
3. 如果还是不确定，再回专题文档看流程与口径。
