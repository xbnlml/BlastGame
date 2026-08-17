# Bot 多线程性能优化计划

## 1. 目标与边界

目标是在不改变 Bot 策略结果、胜率、步数、Replay 签名和 H5 对拍口径的前提下，降低单局 CPU/GC 成本，提高批跑有效并行度，并减少 Unity Editor 卡顿。

范围：

- `Assets/GameModule/Editor/Bot/`
- 必要时 `Assets/GameModule/GameMain/Script/Sim/`

不改变 Runtime 玩法结果，不调整默认 Beam 策略语义。

## 2. 已确认热点

### 2.1 普通块计数全盘校验进入热路径

`BlastGameState.SetBlock`、`SetBlockHealth`、`SetBlockSpecialState` 中的普通块计数断言会调用全盘扫描。该入口会被同色预测副本和 Beam 分支频繁调用，使本应 O(1) 的增量维护退化为 O(棋盘格数)。

诊断断言不得进入预测 Clone、Beam 分支、每次命中和每个 combat tick。

### 2.2 单次 Beam 决策工作量大

默认 `visibleDepth=3`、`visibleWidth=10`。根层可扩展多个候选；后续每层保留 Beam 节点并继续扩展。每个分支会 Clone State、Candidates、Slots 和最近动作，然后执行短/长 settle。

并行粒度是整局 `RunSingle`，单局 Beam 搜索仍串行。因此 worker 数增加只能并行更多局，不能降低一局的决策计算量。

### 2.3 worker 可用率与 Editor 争用

worker 数通常受 `ProcessorCount - 1` 限制。`LongRunning` worker 会长期占用 CPU；当 worker 接近逻辑核数时，Editor 主线程、GC 和进度 UI 的调度余量不足。

自适应批跑按 wave 限制任务领取；当 wave 太小或单局耗时差异较大时，部分 worker 会在 `Monitor.Wait` 中等待，实际并行度低于配置值。

### 2.4 多线程隔离约束

以下容器必须保持每线程或每局独立：

- Bot Clone Pool 的 `BlastGameState`、Candidate、Slot、BeamNode。
- AttackPrediction Scratch、Beam Scratch、AttackSystem Snapshot Pool。
- Board、Slot、AttackSystem 缓存和普通块计数。

禁止新增普通静态可变容器。跨 worker 仅共享只读初始模板和不可变配置快照。

## 3. P0：建立可复现基线

入口：

- `BlastBotRunPolicy.RunSingleBatchParallelWaved`
- `BlastBotService.RunSingleInternal`
- `BlastBotService.ChooseActionBeamGreedyCoreBody`

增加仅 Editor/Development 可用的聚合指标，禁止逐 tick 日志：

- 每局总耗时和每决策耗时。
- 每局 CloneState、CloneCandidates、CloneSlots 次数。
- 同色预测请求、重建、命中、预测 pass 数。
- Beam 根层/深层分支数、保留节点数、settle tick 数。
- 普通块计数全盘校验次数和耗时。
- worker 忙碌时间、wave 等待时间、完成局数。
- 主线程进度 UI 刷新次数和耗时。

基线最小矩阵：

| 维度 | 覆盖 |
|---|---|
| 关卡规模 | 小、中、大盘面 |
| 策略 | ScoringOptVg |
| 批量 | 1、worker 数、worker 数 × 4 |
| 线程 | 1、2、4、CPU-1 |
| 模式 | 固定批跑、自适应 wave、开启/关闭 Trace |

产物：每组一行汇总，包含 wall time、CPU time、GC、runs/min、worker busy/wait 比例。

## 4. P1：移除普通块计数校验的热路径扫描

实施：

1. 保留 `RemainingNormalBlockCount` 的增量维护。
2. 从 `SetBlock`、`SetBlockHealth`、`SetBlockSpecialState` 移除自动全盘扫描断言。
3. 新增显式 Development 验证入口，例如 `ValidateRemainingNormalBlockCount()`。
4. 仅在以下边界校验：
   - 关卡初始化完成。
   - Rollback/Replay restore 完成。
   - Bot 单局结束。
   - 可选的每 N 局采样。
5. 断言失败仅输出一次结构化诊断：cached、scanned、seed、step、是否预测副本、策略、线程 ID。
6. 确认每条 Clone 路径都同步 Board 派生状态：
   - Runtime rollback clone。
   - Bot Clone Pool。
   - 同色预测 clone 间接路径。

验收：

- Bot 预测和 Beam 路径的全盘校验次数为 0。
- 初始化、恢复和单局结束仍可校验一致性。
- 普通块计数不再出现负数。

## 5. P2：限制 Beam 的分支工作量

新增仅用于预算与诊断的参数：

- `maxRootSimulations`
- `maxDepthSimulations`
- `maxSettleTicksPerDecision`
- `maxCloneBytesPerDecision`（估算指标）

实施：

1. 保持现有根层排序和确定性 tie-break；仅在超预算时停止低优先级候选扩展。
2. 根层保留较宽候选集合，深层使用更小 shortlist。
3. 大盘面或目标数高时进一步收窄深层候选数。
4. 普通分支继续短 settle；攻击机会、合并、关键掉落、Closing、终局风险才走长 settle。
5. 终局探针继续完整正时间 settle，禁止为性能降级。
6. 优先减少不会晋级下一层的临时分支 Clone；State/Slot/Board 仍必须独立，禁止共享可变引用。

验收：

- 固定 seed 的第一选择、最终胜负、步数、Replay 签名一致。
- 每决策 Clone 次数、settle tick 数和 P95 决策耗时下降。

## 6. P3：提高批跑有效并行度

实施：

1. 记录每个 worker 的 busy/wait 时间和完成局数。
2. 默认 worker 数调整为 `min(请求值, CPU-2, runCount)`，为 Unity Editor 留出调度余量；保留高级配置显式使用 `CPU-1`。
3. 固定批跑不使用小 wave，连续领取任务。
4. 自适应批跑使用不少于 `workerCount × 2` 的 wave；剩余任务不足时收缩。
5. 保留原子动态领取任务，避免静态切片导致慢 seed 拖尾。
6. 记录慢 seed 和每局 wall time。
7. 不在 P1/P2 完成前实施 Beam 内嵌并行：其会放大 Clone/GC，并增加确定性与 ThreadLocal 池管理风险。

验收：

- 实际活跃 worker 数接近配置值。
- worker 等待占比下降。
- Editor 主线程响应改善。
- 同一 seed 的结果在线程数变化下保持一致。

## 7. P4：GC、日志和 Editor 干扰控制

实施：

1. Batch 默认关闭 `enableDecisionTrace` 和逐步详细日志。
2. Trace 只用于单 seed 定位、失败重放和性能抽样。
3. 复用或池化 `recentActions`、placement scratch、Replay records、Trace DTO 容器。
4. 进度 UI 按时间阈值或完成比例刷新，不在每局完成时同步刷新。
5. 继续在主线程预缓存配置，worker 禁止访问 Unity Object、UIConfig、DataConfig 或 `GameController.Instance`。

验收：

- 无 Trace 的批跑不分配 Trace DTO。
- GC Alloc、Gen2 压力和 UI 刷新频率下降。

## 8. 每阶段共同回归

每阶段均需覆盖：

- 固定 seed 的选列序列、命中顺序、ammo、killed runtimeId。
- 胜负、steps、剩余目标、最终 Board/Slot 签名、Replay 签名。
- 1、2、4、N worker 下每个 seed 的结果一致。
- 多次重复运行，排除线程竞争和非确定性。
- P50/P95 单局耗时、runs/min、预测 pass、Clone、全盘扫描和 worker busy/wait 比例。

## 9. 建议实施顺序

`P0 → P1 → P2 → P3 → P4`

P1 优先级最高：它同时影响真实战斗、同色预测 Clone 和 Beam 分支，收益最大，且不改变策略决策口径。
