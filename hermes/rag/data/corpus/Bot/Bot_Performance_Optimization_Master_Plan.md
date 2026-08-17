# Bot 性能优化总计划

> 更新时间：2026-08-14  
> 适用范围：`Assets/GameModule/Editor/Bot/`；仅在必要时修改 `Assets/GameModule/GameMain/Script/Sim/`。  
> 优化原则：正确性优先，所有无语义优化必须保持逐 seed 结果、动作序列和 Replay/H5 对拍口径一致。

## 1. 总目标与边界

在不改变 Bot 策略结果、胜负、步数、Replay 签名和 H5 对拍口径的前提下：

- 降低单局 CPU、settle 和 GC 成本。
- 提高批跑有效并行度，减少 Unity Editor 卡顿。
- 降低 Beam、Temporal Probe 和 Clone 的内存峰值。
- 保持多线程运行的确定性和线程隔离。

不改变 Runtime 玩法结果，不默认调整 Beam 策略语义，不通过减少可见深度、宽度、Temporal 探测或终局 Probe 换取速度。

## 2. 当前状态与权威结论

### 2.1 第一阶段：历史方案，当前需重新确认

- 以下内容曾在第一阶段接入，但当前代码状态已被重置，不能直接视为仍然存在：
  - 将普通块计数全盘校验移出 `SetBlock`、`SetBlockHealth`、`SetBlockSpecialState` 热路径。
  - 使用长生命周期 worker 池、动态任务领取和 `CPU-2` 默认上限。
  - 固定批跑取消小 wave，自适应批跑使用覆盖多个 worker 的 wave。
  - 加入 `maxRootSimulations`、`maxDepthSimulations`、`maxSettleTicksPerDecision`、`maxCloneBytesPerDecision` 诊断参数。
  - 保持 Clone Pool、Beam Scratch、Attack Scratch 的 ThreadLocal 或每 worker 隔离。
  - 加入 `TEMP-BOT-PERF-LOG` 临时聚合日志。

这些内容必须先根据当前代码逐项复核并重新接入；在复核完成前，不得把第二阶段的 Temporal、Depth 或 settle 优化当作已具备前置条件。

原交接文档中的“6 workers 已接近满载且负载均衡正常”属于历史基线结论，恢复阶段需要重新测量。只有确认调度恢复后，才能继续判断线程调度是否不是主要瓶颈。

### 2.2 历史权威基线（恢复后必须重测）

历史测试条件：`ScoringOptVg`，L100，400 局，6 workers。以下数据仅用于恢复前后的对照，不代表当前代码状态。

| 指标 | 当前值 | 判断 |
|---|---:|---|
| 批次 wall time | 164.2s | 总体优化基线 |
| 单局平均 | 2451.9ms | 需降低 |
| P95 单局 | 2995ms | 需降低长尾 |
| decision 平均 | 2128.5ms，占 86.8% | 决策是首要范围 |
| depth | 1402.9ms，占决策 65.9% | 第一 CPU 热点 |
| temporal | 541.8ms，占决策 25.5% | 第二 CPU 热点 |
| beam settle | 1241.1ms/局 | 主要模拟成本 |
| settle ticks | 约 30,852/局 | 需定位来源 |
| CloneState | 约 669/局 | 搜索和 Probe 压力大 |
| Clone 估算量 | 约 7.8MB/局 | 需降低峰值 |
| worker 利用率 | 99.6% | 调度已正常 |
| worker 等待 | 0ms | 不存在 wave/锁等待瓶颈 |
| 批次 GC | 841/841/841 | 需区分频率与停顿原因 |

计时口径：`root/depth/temporal` 是互斥的决策高层计时；`beamSettle` 嵌套在模拟中，不能与三者相加；`liveSim` 可能被 Temporal Probe 计入，也不能直接与总耗时相加。`batchGc` 是进程级批次指标，`batchManagedDeltaBytes` 不是总分配量，`cloneEstimateBytes` 只是估算值。

## 3. 总体实施路线

```text
R0 恢复第一阶段改动并重新建立基线
  -> P0 正确性护栏与基线
  -> P1 细化热点计数
  -> P2 Temporal Probe 无语义优化
  -> P3 Depth Beam 生命周期与内存优化
  -> P4 Settle 热路径优化
  -> P5 GC 与 Clone Pool 收尾
  -> P6 可选搜索预算实验（默认关闭）
```

R0/P0/P1 是恢复、诊断与护栏阶段，P2-P5 只做不改变语义的优化，P6 才允许讨论策略结果变化。

### R0：恢复第一阶段并重新建立基线

目标：确认被重置的第一阶段能力是否需要完整恢复，并让后续基线与当前代码一致。

实施顺序：

1. 检查普通块计数校验是否重新进入热路径；若已进入，恢复增量维护与边界显式校验方案。
2. 检查 worker 池、动态任务领取、默认 worker 上限和 wave 策略；不直接假设原实现仍在。
3. 检查 Beam 诊断预算参数、ThreadLocal/每 worker Scratch 与 Clone Pool 隔离；缺失项按原方案重新接入。
4. 重新接入临时聚合日志，并确认 `[BotPerf]`、`[BotPerfPhase]` 的计时口径有效。
5. 重新执行编译、固定 seed 正确性样本和 L100×400×6 基线。
6. 只有恢复后的基线确认 worker 调度正常，且各阶段指标可解释，才进入 P0/P1。

R0 不允许同时做 Temporal、Depth、settle 或搜索预算优化；每项恢复改动单独验证，避免无法区分“恢复收益”和“新优化收益”。

## 4. 各阶段计划

### P0：固定基线与逐 seed 正确性护栏

目标：任何性能改动都能快速发现结果漂移。

实施：

1. 保留 L100×400×6 权威基线，至少重复 3 次，记录 wall、P50、P95 波动范围。
2. 从基线固定至少 20 个样本，覆盖胜局、败局、P50、P95 和最慢 seed。
3. 保存每个样本的 seed、won、steps、endReason、queueRemaining、剩余目标和最终 Board/Slot 指纹。
4. 选择 3–5 个代表 seed 开启 Decision Trace，保存 action 序列和 Replay 签名。
5. 每次补丁先跑样本，再跑 L100×400；发现漂移时定位第一个差异 seed。

完成标准：有可自动或半自动比较的逐 seed 结果表，且基线可稳定复现。

### P1：细化热点与 Clone 来源

目标：说明 settle tick 和 Clone 的真实来源，不先改变策略。

新增聚合指标：

- root/depth/temporal 的调用数、CloneState 数、settle 调用数和 settle tick 数。
- Temporal 的 action 数、delay 数、累计推进时间和提前结束次数。
- Beam settle 的短 settle、长 settle、提前退出和 maxTicks 命中次数。
- settle 退出原因：won、stable、no attack、transient、max_ticks。
- Depth 每层 parent、child、晋级和立即淘汰数量。
- Clone Pool miss、新建容量扩张和峰值租用量。

只记录聚合数据，禁止逐 decision/tick 日志。完成后必须能解释约 30,852 个 settle tick/局分别来自哪些阶段。

### P2：Temporal Probe 无语义优化

目标：将 temporal 平均耗时从 541.8ms/局降低至少 30%，不改变 penalty。

按顺序实施：

1. 复用 delays、after/probe 快照和容量，消除每个 action 的容器扩容。
2. 评估 `CloneSpecialFocusByColor`、`CloneNormalAttackQueueSnapshot` 是否可在 Temporal Scratch 中复用；每次必须完全覆盖，禁止跨 worker 共享。
3. 评估 after Clone 到 probe Clone 的恢复式 scratch 构造；只有状态完全覆盖且成本更低时采用。
4. 评估复用根层同 action 的落子后快照；必须确认 cooldown、rowSweep、specialFocus、normalAttackQueue、spawnContext 和非攻击态折叠一致。
5. 只有在 `maxPenalty` 已达到严格不可超越的最终上界时，才允许提前结束 delay。
6. 检查 `CountLegalColumns`、`ProgressRatio`、`HasAttackOpportunityLikeH5` 的同一 delay 重复扫描，可共享同轮派生结果，但不可跨状态复用。

禁止删除 delay、减少 top-K、缩短推进时间或改变 penalty 权重。Temporal delay 已按升序在同一个 probe 上增量推进，不重复实现该优化。

### P3：Depth Beam 生命周期与内存优化

目标：降低 depth 成本、Clone 峰值和 GC，不先减少搜索分支；wall time 目标至少下降 10%。

实施：

1. 将“保存全部 child、排序、释放尾部”改为容量为 `takeW` 的稳定 Top-K 容器。
2. child 评分后立即比较，未晋级节点立即归还 State、Candidate、Slot、RecentActions 和 BeamNode。
3. 稳定 Top-K 必须保持当前排序和 tie-break：分数相同按原插入顺序，节点集合和顺序与旧实现一致。
4. 诊断模式下与旧排序并行比对，只记录 mismatch 计数。
5. 复用 `depthLegal`、`nextActions` 和临时 set；检查异常、continue、break 路径均归还 Pool。
6. 确认晋级 BeamNode 不引用已归还的 specialFocus、normalAttackQueue 快照。
7. 依据峰值数据预热 ThreadLocal 容器，避免每局重复扩容。

该阶段主要降低内存峰值和 GC，不承诺直接减少 settle CPU。

### P4：Settle 热路径优化

目标：降低 `beamSettle=1241.1ms/局`，使 settle tick 数或单 tick CPU 至少下降 20%。

实施顺序：

1. 依据 P1 的退出原因，先处理占比最大的 settle 类别。
2. 检查 `ShouldContinueSettleAfterTick`、`HasAttackOpportunity` 和 transient 判断的重复 Board/Slot 扫描，复用同一 tick 已生成的结果。
3. 检查 `RunBotCombatTick` 中 `BuildCombatSlotsForTick`、blocked/masked scratch 的清空和扩容，改为 ThreadLocal scratch 并完全覆盖。
4. 为 dt=0 Beam oracle 增加严格的“状态无变化”短路；只有攻击队列、冷却、slot life state、pending unlock、掉落和 transient 均不可能推进时才退出。
5. 单 tick 内可缓存 `CountRemainingNormalBlocks` 等派生值，但禁止跨 tick 或跨 state 缓存。
6. 正时间 terminal Probe 保持原样并单独统计，不纳入 Beam 快速路径优化。

禁止直接降低 `beamSettleMaxTicks`、缩短长 settle、忽略 Closing/合并/掉落/攻击机会。

### P5：GC 与 Clone Pool 收尾

目标：L100×400 批次 GC 次数下降至少 30%，无 Pool 泄漏、引用污染或结果漂移。

实施：

1. 根据 Pool miss 和容量数据预热，禁止无上限扩大池。
2. 检查 `CloneCandidates` 的邻居索引、队列、special focus 和 normal attack snapshot 的深拷贝分配。
3. 固定长度五槽数据优先使用 struct 或预分配数组，避免短命 Dictionary/List。
4. `captureTrace=false` 时不创建 Trace DTO、tickLog 和 breakdown Dictionary。
5. 使用 Unity Profiler 的 GC Alloc、Managed Heap、GC.Collect marker 复核；`batchManagedDeltaBytes` 仅作辅助。
6. 池化后执行多线程重复测试，检查归还后的引用、跨 seed 污染和确定性。

### P6：可选搜索预算实验

默认关闭，仅在 P2-P5 收益不足且用户明确接受结果变化时执行。所有实验必须独立开关，并输出逐 seed、胜率和 Replay 差异。

可实验项：大盘面动态 `maxDepthSimulations`、更小的 depth shortlist、基于确定上界的 branch-and-bound、Temporal top-K 或 delay 集合调整。不得与无语义优化混入同一提交。

## 5. 统一正确性与性能验收

必须通过：

- 固定 20 个样本 seed 的全部结果字段一致。
- Trace 样本的 action 序列、Beam 选择和 Replay 签名一致。
- L100×400 逐 seed 一致，而非只比较总胜率。
- 1 worker 与 6 workers 逐 seed 一致。
- 同配置重复 3 次无竞态、异常或 Pool 污染。
- Unity 重新编译无错误，`git diff --check` 通过。

方向性性能目标：

| 指标 | 当前 | 第一目标 | 最终目标 |
|---|---:|---:|---:|
| L100×400 wall | 164.2s | ≤140s | ≤123s |
| runAvg | 2451.9ms | ≤2100ms | ≤1800ms |
| P95 | 2995ms | ≤2600ms | ≤2300ms |
| decisionAvg | 2128.5ms | ≤1800ms | ≤1550ms |
| depth | 1402.9ms | ≤1150ms | ≤950ms |
| temporal | 541.8ms | ≤380ms | ≤300ms |
| batch GC | 841 | ≤650 | ≤500 |
| workerUtil | 99.6% | ≥95% | ≥95% |

正确性优先：结果漂移时，即使性能更快，也不能合入无语义优化阶段。

## 6. 每个补丁的执行模板

1. 说明只优化一个热点，以及为什么不改变语义。
2. 保存相同配置的修改前基线。
3. 使用 `apply_patch` 做最小修改，并执行 `git diff --check`。
4. Unity CLI 重新编译，确认无编译错误。
5. 跑固定 seed 样本，比较逐 seed 结果。
6. 跑 1 worker 与 6 workers 一致性。
7. 跑 L100×400×6，记录 `[BotPerf]` 和 `[BotPerfPhase]`。
8. 记录耗时、GC、Clone、settle 和结果差异；无收益或有漂移只回退当前补丁。
9. 一次只提交一个可解释的优化点，不把预算调整与池化混在一起。

## 7. 临时日志移除条件

只有在最终基线已保存、正确性矩阵全部通过、热点和收益已归因且不再需要阶段指标后，才移除 `TEMP-BOT-PERF-LOG`。移除后再次执行 Unity 编译、`git diff --check` 和最小 Bot 批跑。

临时日志定位：

```text
rtk rg -n "TEMP-BOT-PERF-LOG|\[BotPerf\]|\[BotPerfPhase\]" Assets/GameModule/Editor/Bot
```
