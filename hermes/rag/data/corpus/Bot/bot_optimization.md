# Bot 优化器当前使用说明


## 优化器职责分层

- Workbench/UI 层：参数输入、任务触发、进度反馈与结果入口。
- Optimizer 层（`BlastMultiTierOptimizer` / `BlastOptimizerService`）：候选生成、阶段筛选、统计评估与选档。
- Runner 层（批跑/Jenkins）：区间任务编排、并发控制、落盘与状态汇总。

## 协作边界

- 优化器只搜索参数，不改 Runtime/Sim 规则。
- 评分仅基于约定指标（目标胜率贴合度、失败分布偏差等），不通过改规则“刷胜率”。
- 结果输出必须可按 level/tier/seed 复查，不能只保留最终汇总。

## 阶段职责

- Phase0：现配基线评估与去重复用。
- Phase1：广覆盖采样，建立候选池。
- Phase2：追加评估并收敛候选。
- Phase3：最终候选确认与导出（按当前实现口径）。

## 适用范围

本文只说明当前 Workbench / Jenkins 优化器的参数和输出，不记录历史调参过程、旧评分公式或单次批跑结果。

## 1. 优化入口

| 场景 | 入口 |
|---|---|
| Unity Workbench | `BlastOptimizerService` 与对应 Editor Window |
| Multi-Tier | `JenkinsRunMultiTierOpt.sh` |
| Run-Level-Tier | `JenkinsRunBlastBotBatchRange.sh` |
| 结果检查 | `BlastCheckTool.py` 与批跑分析脚本 |

## 2. 参数分组

### 搜索预算

- `runs`：每个配置的模拟局数。
- `maxSteps`：单局最大步数；`0` 表示不限制。
- `beamWidth` / `beamDepth`：搜索宽度和深度。
- `MAX_WORKERS`：并行 worker 数。

预算只改变采样和搜索成本，不改变玩法规则。

### 难度参数

- `StartDifficulty`
- `ShuffleSplitCount`
- `ShuffleSplitRatios`
- `ShuffleOverflowFactor`
- `DifficultyLevel`

难度配置必须按关卡和 tier 读取，不能在优化器中复制动态难度公式。

### 目标与评分

- `targetWinRate`：目标胜率。
- `winRateMatch`：结果与目标胜率的接近程度。
- `failDist`：失败分布偏差。
- 评分器当前实现见 `Bot_Architecture.md` 和 `Assets/GameModule/Editor/Bot/Scoring/`。

## 3. 执行与输出

每个批次至少记录：

- level / tier / strategy；
- seed 范围和运行数量；
- win、loss、end reason；
- 目标胜率、实际胜率和偏差；
- 输出目录和配置来源；
- 本关 telemetry 下的 `level-assets/{levelGroup}/{gameLevel}.asset`（构造时快照的 `LevelProfileConfig`）。

批次结果必须能按关卡、tier 和 seed 复查，不能只保留最终档位。

## 4. 结果检查

1. 检查输入配置和关卡编号是否一致。
2. 检查是否发生重复 `ConfigKey`。
3. 检查运行数量、成功数和失败数是否闭合。
4. 对异常胜率按 seed 复跑。
5. 确认优化前后 Bot 与 Runtime 规则一致。

## 5. 优化边界

- 不修改 Runtime/Sim 玩法规则。
- 不为了提高胜率隐藏失败、改变 end reason 或跳过状态推进。
- 不把一次实验结论写入当前规则文档。
- 性能优化只能减少分配、重复计算和外层输出，不能改变动作选择语义。

## 6. Jenkins Multi-Tier 准备耗时锚点

定位「Job 开始 → 首关」空档时，只看 `[MultiTierTiming]`（**中国时区 +08**），不要靠猜。

格式：`[MultiTierTiming] stage=... at=YYYY-MM-DD HH:MM:SS +0800 elapsedSec=N`

| stage | 含义 | `elapsedSec` |
|---|---|---|
| `shell_enter` | 批跑脚本开始（Jenkins SCM checkout 已结束） | 0 |
| `submodule_update_done` | `git submodule update --init` + reset 结束 | 本段秒数 |
| `submodule_fetch_done` | tracking branch wipe+fetch 结束 | 本段秒数 |
| `unity_spawn` | 即将启动 Unity | 自 `shell_enter` |
| `execute_method` | C# `RunFromCommandLine` 入口 | 0（C# 侧原点） |
| `excel_loaded` | Excel TryLoad 成功 | TryLoad 秒数 |
| `first_level_loaded` | 第一个关卡 SO 加载成功（只打一次） | 自 `execute_method` |

读法：

1. **Job Started（Jenkins UI）→ `shell_enter.at`**：插件侧 `git fetch/checkout` 墙钟。
2. **`shell_enter` → `submodule_*`**：submodule / 可能的 LFS。
3. **`unity_spawn.at` → `execute_method.at`**：Unity 进程冷启动。
4. **`execute_method` → `first_level_loaded`**：C# 准备（含 Excel）；预期秒～十秒级。

未定位前不要改 submodule/SCM/模拟逻辑；先凭上述墙钟差定瓶颈再改。
