# Game Analysis Logic（分析诊断）

本文对应 `Playbooks/game-analysis-logic.md`，聚焦“运行时队列/性能日志、对拍产物解读与排障入口”。

## 1. 主要分析维度

- 队列构建与候选消耗一致性。
- 攻击/落块推进时序正确性。
- 回放一致性（动作协议、时序、结果）。
- 动态难度参数生效口径（tier、offset、配置档位）。

## 2. 推荐观测入口

- 热键：
  - `R`：重开当前关
  - `N`：下一关
  - `L`：触发一次 key-lock 配对
  - `P`：读取本地最新回放并开始/中止回放
  - `G`：切换 HUD 显示
- 运行配置：
  - `BlastUIRuntimeConfig.logQueueDebug`
  - `BlastUIRuntimeConfig.logLoadPerformance`
- 工具命令（config 只读对账）：
  - `python Tools/Python/GameTools/BlastCheckTool.py asset-final-parity --asset "<level.asset>"`
  - `python Tools/Python/GameTools/BlastCheckTool.py asset-final-parity --series funnel_b --start 1 --end 200 --format json --out "Temp/funnel_b_asset_final_parity.json"`
  - 用途：快速定位“上下区按颜色总量不一致”与 `TriangleOnly` 风险缺口。

## 3. 排障文档锚点

- Board/Stage 区域流程图：`Doc/MainGame/GM_Board_Stage_Flow.md`
- 回放链路与协议：`Doc/MainGame/Blast_Replay.md`
- 动态难度机制：`Doc/MainGame/Blast_DynamicDifficulty.md`
- 主流程总览：`Doc/MainGame/Gameplay_Flow_Logic.md`

## 4. 基础排查顺序

1. 先确认日志开关是否开启（队列/加载性能）。
2. 再确认输入状态（关卡配置、候选、槽位、回放文件）是否一致。
3. 最后对照流程图与回放动作序列定位偏差点（流程阻塞、动作未派发、结果口径不一致）。

## 5. 类功能定位

| 类/文件 | 功能 | 路径 |
|---|---|---|
| `BlastQueueBuilder` | 运行时队列构建与 Pool 队列提取 | `Assets/GameModule/GameMain/Script/Sim/BlastQueueBuilder.cs` |
| `BlastGameController.Loading` | 加载性能日志与关卡加载阶段诊断 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Loading.cs` |
| `BlastReplayFlowCoordinator` | 回放推进状态决策（started/stalled/finished） | `Assets/GameModule/GameMain/Script/Runtime/BlastReplayFlowCoordinator.cs` |
| `BlastReplayRecordAdapter` | 回放录制动作映射与写入桥接 | `Assets/GameModule/GameMain/Script/Runtime/BlastReplayRecordAdapter.cs` |

维护规则：新增诊断入口（日志、导出、对拍）后，需在本表补对应类与路径。
