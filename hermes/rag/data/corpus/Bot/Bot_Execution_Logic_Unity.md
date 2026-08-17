# Unity Bot 执行链路


## 执行链路职责

- Unity Editor 层：参数装配、任务调度、日志导出。
- Bot/Sim 层：单局状态初始化、动作决策、combat/settle 推进与终局判断。
- 批跑层：重复单局流程并聚合统计，不改单局规则。

## 一致性协作边界

- 单局入口统一 `BlastBotService.RunSingle(...)`，批跑入口在外层循环调用单局。
- Runtime 一致性要求：攻击机会、可落列、settle 顺序、终局分类必须与 Runtime 同口径。
- “优先复用运行时路径”原则：若 helper 与 Runtime 规则重复，优先替换为共享实现调用。

## 分层约束

- Editor 参数（如 maxSteps/beam）只影响预算，不得改变规则。
- human-window 只影响仿真时间轴，不引入线程睡眠或信息边界变化。
- trace/replay 只做诊断，不参与评分和动作选择。

## 适用范围

本文说明 Unity Editor 中如何驱动 Bot 单局与批跑。Bot 架构、规则一致性和评分口径见 [`Bot_Architecture.md`](Bot_Architecture.md)。

## 1. 执行入口

| 场景 | 当前入口 |
|---|---|
| 单局 | `BlastBotService` |
| 区间批跑 | `BlastBotRangeRunner` |
| Workbench | `BlastOptimizerService` 与对应 Editor Window |
| Jenkins | `Tools/Python/jenkins-batch/` 下的批跑脚本 |

Unity 层只负责参数装配、任务调度、日志和结果导出；玩法推进由 Bot/Sim 代码完成。

## 2. 单局流程

1. 读取关卡和运行参数。
2. 生成 seed 并构造 `BlastBotRunOptions`。
3. 调用 `BlastBotService` 初始化状态。
4. 按策略循环执行候选动作和 combat tick。
5. 在胜利、失败或无动作时结束。
6. 输出结果、结束原因和必要的 trace/replay。

批跑只是在外层重复该流程，并聚合 win rate、end reason、耗时和错误。

## 3. 关键参数

### 搜索与预算

- `maxSteps = 0` 表示不限制步数，不要自动改成 1。
- `beamWidth`、`beamDepth`、`topK` 控制候选搜索规模。
- 预算只影响搜索范围，不得改变规则和状态转移。

### 评分与进度

- `progressRatio` 遵循当前 H5/Runtime 口径，允许出现负值，不在 Editor 层强制 clamp。
- 评分参数必须从运行配置读取，不使用硬编码占位值。
- `mergeBonus`、Gate 阻塞、Snake 颜色感知等规则以当前评分器实现为准。

### 随机与人类窗口

- seed 必须传入并记录。
- `scoring_opt_vg` 的 human-window 只影响时间轴和动作延迟，不改变可见信息边界。
- 延迟量化必须使用当前运行参数，不调用线程休眠。

## 4. 一致性要求

- Bot 真局使用与 Runtime 相同的 `BlastGameLogic.TickCombat`。
- `AdvanceSlotStates` 在 `UpdateAttacks` 前执行。
- Beam/lookahead 使用独立快照；评估结果不能写回真局。
- `BlastAttackSystem`、队列、特殊块和放置状态的规则不在 Unity Editor 层复制。

## 5. 输出契约

每局结果至少包含：

- level、strategy、seed；
- win / loss；
- end reason；
- steps、耗时或仿真时间；
- 必要时的 trace/replay 路径。

批跑输出必须能按 seed 复查，避免只输出汇总数字而无法定位分歧。

## 6. 验收

- 同一关卡、策略和 seed 可重复得到相同结果。
- 单局和批跑的参数解释一致。
- `maxSteps=0` 的语义正确。
- 进度、延迟、随机数和评分没有被 Editor 层二次改写。
- Bot 与 Runtime 的状态推进顺序一致。
- 性能优化只减少分配和外层开销，不改变胜率或动作序列。
