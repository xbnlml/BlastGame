# Bot 性能第二阶段优化计划与 Agent 交接

> 更新时间：2026-08-14  
> 适用范围：`Assets/GameModule/Editor/Bot/`，仅在必要时修改 `Assets/GameModule/GameMain/Script/Sim/`。  
> 前置计划：[Bot_Multithread_Performance_Optimization_Plan.md](Bot_Multithread_Performance_Optimization_Plan.md)

## 1. 新 Agent 先读

本任务已经完成第一阶段多线程调度和性能诊断，不要重新实现 worker 池，也不要先增加线程数。

当前 worktree 包含尚未提交的用户改动和本任务改动。禁止 reset、restore 或覆盖现有文件；必须在当前状态上继续。

本阶段唯一目标：在保持 Bot 决策结果、胜负、Replay/H5 对拍口径不变的前提下，降低单局 `ScoringOptVg` 的决策、深层 Beam、Temporal Probe 和 settle 成本。

## 2. 当前上下文总结

### 2.1 已完成事项

第一阶段已实施：

- 普通块计数全盘校验已从热路径移除，改为初始化、恢复和 Bot 单局结束时显式校验。
- 固定批跑使用长生命周期 `LongRunning` worker 池和动态任务领取。
- worker 默认上限为 `min(请求值, runCount, CPU-2)`，为 Unity Editor 留核。
- 固定批跑不再使用小 wave；自适应批跑的 wave 至少覆盖多个 worker。
- Beam 参数已支持诊断预算：`maxRootSimulations`、`maxDepthSimulations`、`maxSettleTicksPerDecision`、`maxCloneBytesPerDecision`。
- Clone Pool、Beam Scratch、Attack Scratch 等保持 ThreadLocal/每 worker 隔离。
- 已加入临时聚合性能日志，统一使用 `TEMP-BOT-PERF-LOG` 标记。
- Unity 6.0.60f1 已重新编译通过；当前 Editor 可直接运行机器人测试。

主要相关文件：

- `Assets/GameModule/Editor/Bot/BlastBotBatchRunner.cs`
- `Assets/GameModule/Editor/Bot/BlastBotRunPolicy.cs`
- `Assets/GameModule/Editor/Bot/BlastBotService.cs`
- `Assets/GameModule/Editor/Bot/BlastBotService.Decision.cs`
- `Assets/GameModule/Editor/Bot/BlastBotService.Simulation.cs`
- `Assets/GameModule/Editor/Bot/BlastBotService.SimulationTail.cs`
- `Assets/GameModule/Editor/Bot/BlastBotService.RunModels.cs`
- `Assets/GameModule/Editor/Bot/BlastBotService.RunOptions.cs`
- `Assets/GameModule/Editor/Bot/Scoring/BlastBotScoring.Penalties.cs`
- `Assets/GameModule/Editor/Bot/Pool/BlastBotClonePool.cs`

### 2.2 当前日志口径

机器人批跑结束后输出两类日志：

- `[BotPerf]`：批次 wall time、单局 P50/P95、决策和 settle、Clone 次数、批次 GC、worker busy/wait 和负载分布。
- `[BotPerfPhase]`：legal、frame、hold、subset、root、depth、score、temporal、select、liveSim、beamSettle 阶段耗时。

重要口径：

- `root/depth/temporal` 是决策阶段的互斥高层计时，可用于定位决策热点。
- `beamSettle` 嵌套在 root、depth、temporal 的模拟中，不能再与三者相加。
- `liveSim` 也可能被 Temporal Probe 内部的 `AdvanceCombatWindow` 计入，不能与总耗时直接相加。
- `batchGc=a/b/c` 是整个批次的进程级 GC 次数，不再累加并发单局采样。
- `batchManagedDeltaBytes` 是批次前后存活托管堆变化，不是总分配量；负数表示批次结束时存活堆更小。
- `cloneEstimateBytes` 是按棋盘尺寸估算的 Clone 工作量，不是真实 GC Alloc。

所有临时日志移除入口：

```text
rtk rg -n "TEMP-BOT-PERF-LOG|\[BotPerf\]|\[BotPerfPhase\]" Assets/GameModule/Editor/Bot
```

最终优化验收完成前不要移除日志。

## 3. 最新权威基线

测试条件：`ScoringOptVg`，L100，400 局，6 workers。

```text
[BotPerf] strategy=scoring_opt_vg level=100 runs=400/400 workers=6 wallMs=164185 runAvgMs=2451.9 p50Ms=2465 p95Ms=2995 decisionAvgMs=2128.5 decisionPct=86.8% beamSettleAvgMs=1241.1 beamSettlePct=50.6% settleTicks=12340826 cloneState=267524 cloneCandidates=267524 cloneSlots=267524 cloneRecent=237124 cloneEstimateBytes=3116119552 batchManagedDeltaBytes=85495808 batchGc=841/841/841 workerBusyMs=980763 workerBusyMinMs=163023 workerBusyMaxMs=164146 workerRuns=65-68 workerWaitMs=0 workerUtil=99.6% waitRatio=0.0%

[BotPerfPhase] strategy=scoring_opt_vg level=100 avgMs=legal=0.1 frame=0.3 hold=0.1 subset=0.7 root=143.9 depth=1402.9 score=0.0 temporal=541.8 select=0.0 decisionOther=38.7 liveSim=692.9 beamSettle=1241.1
```

派生指标：

| 指标 | 数值 | 结论 |
|---|---:|---|
| 总墙钟 | 164.185 秒 | 后续优化的主基线 |
| worker 利用率 | 99.6% | worker 数量和调度不是瓶颈 |
| worker 局数 | 65–68 | 动态领取负载均衡正常 |
| worker 等待 | 0 ms | 不存在 wave/锁等待问题 |
| 决策占单局 | 86.8% | 优先优化决策，不优化导出/UI |
| Depth 占决策 | 65.9% | 第一 CPU 热点 |
| Temporal 占决策 | 25.5% | 第二 CPU 热点 |
| Depth + Temporal | 91.4% 决策时间 | 优化范围已经收敛 |
| settle tick/局 | 约 30,852 | Beam/Probe 模拟量过大 |
| CloneState/局 | 约 669 | 搜索分支和 Probe Clone 压力大 |
| Clone 估算/局 | 约 7.8 MB | 需降低活跃 Clone 和快照复制 |
| 批次 GC | 841/841/841 | GC 频率高，但需单独区分原因与停顿 |

## 4. 已确认调用链

```text
BlastBotBatchRunner.Run
  -> BlastBotRunPolicy.RunSingleBatchParallelWaved
    -> BlastBotService.RunSingleInternal
      -> ChooseActionBeamGreedyCoreBody
        -> 根层 Clone + SettleCombatFully + EvaluateGreedy
        -> 深层 Clone + SettleCombatFully + EvaluateGreedyDeep
        -> TemporalWindowPenaltyForAction（top-K 动作）
          -> 再次 Clone State/Candidates/Slots/RecentActions
          -> ClickCandidateColumn
          -> RunBotCombatTick(dt=0)
          -> Clone Probe State/Candidates/Slots
          -> 按升序 delay 增量调用 AdvanceCombatWindow
        -> 选择最终 action
```

关键实现事实：

- Temporal 多 delay 已经按升序在同一个 probe 上增量推进，不要重复实现该优化。
- Temporal 仍会为每个被探测 action 创建 after Clone 和 probe Clone，并推进多段 combat window。
- Depth 当前先生成所有 child、加入 `next`、排序，再释放超过 `takeW` 的节点。
- 每个 child 都要 Clone、点击、settle、评分后才知道是否晋级；因此减少存活对象和分配比盲目缓存分数更安全。
- `RunBeamSettleTicksCore` 每 tick 调用 `RunBotCombatTick` 和 `ShouldContinueSettleAfterTick`。
- 终局 Probe 使用正时间完整 settle，不能与 Beam 的 dt=0 oracle 合并或缩短。

## 5. 约束与非目标

必须保持：

- 同一 seed 的最终胜负、steps、endReason、queueRemaining、剩余目标一致。
- 同一 seed 的选择动作序列一致；抽样开启 Trace 时 Beam 排序、tie-break 和 Replay 签名一致。
- 1 worker 与 6 workers 结果一致，多次重复运行无竞态。
- H5 可见信息、HumanWindow、Temporal delay 集合和评分口径不变。
- ThreadLocal Pool/Scratch 隔离；worker 不读取 Unity Object、UIConfig、DataConfig 或 `GameController.Instance`。

本阶段不做：

- 不继续增加 worker 数。
- 不做 Beam 内部分支并行。
- 不默认缩小 `visibleDepth`、`visibleWidth` 或 Temporal top-K。
- 不通过关闭 HumanWindow、Temporal Probe、攻击模拟或终局 Probe 换速度。
- 不以单次胜率接近代替逐 seed 一致性。

## 6. 实施计划

### P0：固定基线和逐 seed 一致性护栏

目标：任何性能改动都能判断是否改变结果。

实施：

1. 保留上述 L100×400×6 基线日志。
2. 从这 400 个 seed 中固定至少 20 个样本：覆盖胜局、败局、P50、P95 和最慢 seed。
3. 为样本保存：seed、won、steps、endReason、queueRemaining、finalTargetUnitRemaining、最终 Board/Slot 指纹。
4. 选 3–5 个代表 seed 开启 Decision Trace，保存 action 序列和 Replay 签名。
5. 每次补丁先跑样本，再跑 L100×400；失败时立即定位第一个漂移 seed。
6. 基线至少重复 3 次，记录 wall/P50/P95 波动范围，避免把机器抖动当收益。

完成标准：存在可自动或半自动比较的逐 seed 结果表；优化前基线可稳定复现。

### P1：细化热点计数，不先改策略

目标：区分 Depth/Temporal 的模拟数量、settle 退出原因和 Clone 来源。

新增聚合指标：

- root/depth/temporal 各自的调用数、CloneState 数、settle 调用数、settle tick 数。
- Temporal 每局探测 action 数、delay 数、累计推进毫秒、提前结束次数。
- Beam settle 的短 16 tick、长 cap、实际提前退出和 maxTicks 命中次数。
- settle 退出原因分布：won、stable、no attack、transient、max_ticks。
- Depth 每层 parent 数、child 数、晋级数、立即淘汰数。
- Clone Pool miss、新建容量扩张和峰值租用量。

要求：只记录聚合计数，禁止逐 decision/tick 打日志。

完成标准：能回答“12,340,826 个 tick 分别来自 root、depth、temporal、live/terminal 的多少”。

### P2：Temporal Probe 无语义优化

目标：优先把 `temporal=541.8ms/局` 降低，不改变 penalty。

按以下顺序实施，每项独立验证：

1. 复用 Temporal 的 delays 容器、after/probe 辅助快照和容量，消除每 action 的容器扩容。
2. 检查 `CloneSpecialFocusByColor`、`CloneNormalAttackQueueSnapshot` 是否可在 Temporal Scratch 中复用目标容器；保持每次内容完全覆盖，禁止跨 worker 共享。
3. 将 after Clone 到 probe Clone 的复制改为直接从同一已落子 after 状态构造可恢复 scratch；只有证明恢复成本低于 Clone 且状态完全覆盖时才采用。
4. 评估是否能复用根层同 action 的“落子后、任何 settle 前”快照。必须确认 cooldown、rowSweep、specialFocus、normalAttackQueue、spawnContext 和非攻击态折叠完全一致；不一致则禁止复用。
5. 对 penalty 上界做数学分析。只有当前 `maxPenalty` 已达到严格不可超越的最终上界时，才允许提前结束后续 delay。
6. 检查 `CountLegalColumns`、`ProgressRatio`、`HasAttackOpportunityLikeH5` 在同一 delay 上是否存在重复全盘扫描；可共享同一轮派生结果，但不能跨状态复用。

禁止事项：删除 delay、减少 top-K、降低推进时间或改变 penalty 权重。

阶段目标：Temporal 平均耗时下降至少 30%，固定 seed 结果完全一致。

### P3：Depth Beam 生命周期与内存优化

目标：降低 `depth=1402.9ms/局`、Clone 峰值和 GC，不先减少搜索分支。

按以下顺序实施：

1. 将每层 `next` 的“保存全部 child → 排序 → 释放尾部”改为容量为 `takeW` 的稳定 Top-K 容器。
2. 每个 child 完成评分后立即与当前 Top-K 比较；未晋级节点立即归还 State/Candidate/Slot/RecentActions/BeamNode。
3. Top-K 比较必须复刻当前稳定排序：分数相同按原插入顺序，最终节点集合和顺序与旧实现完全一致。
4. 对照旧实现同时运行一段时间：诊断模式下计算旧排序结果与新 Top-K 结果，只记录 mismatch 计数。
5. 复用每层 `depthLegal`、`nextActions` 和临时 set 容器，检查所有异常/continue/break 路径都归还 Pool。
6. 检查 BeamNode 中 specialFocus、normalAttackQueue 快照的所有权；淘汰节点必须立即归还，晋级节点不能引用已归还容器。
7. 记录 Pool miss 和 List Capacity 扩张，按 L100 峰值预热 ThreadLocal 容器容量，避免每局重复扩容。

注意：Top-K 生命周期优化主要降低内存峰值和 GC，不一定减少 settle CPU；这是后续安全剪枝的前置工作。

阶段目标：Depth 结果完全一致；批次 GC 明显下降；wall time 至少下降 10%。

### P4：Settle 热路径优化

目标：降低嵌套在 Beam/Temporal 内的 `beamSettle=1241.1ms/局`。

实施顺序：

1. 用 P1 数据确认 tick 来源和退出原因，优先处理占比最大的 settle 类别。
2. 检查 `ShouldContinueSettleAfterTick`、`HasAttackOpportunity`、transient 判断是否重复扫描 Board/Slots；在同一 tick 内复用已经生成的 combat 结果和派生状态。
3. 检查 `RunBotCombatTick` 内 `BuildCombatSlotsForTick`、blocked/masked scratch 是否在 Beam 路径重复清空或扩容；改为 ThreadLocal scratch 并完全覆盖内容。
4. 对 dt=0 Beam oracle 增加严格的“状态无变化”短路：只有攻击队列、冷却、slot life state、pending unlock、掉落和 transient 均不可能推进时才能退出。
5. 缓存单 tick 内 `CountRemainingNormalBlocks` 等派生值，禁止跨 tick/跨 state 缓存。
6. 保持正时间 terminal probe 原样，单独统计，不纳入 Beam 快速路径优化。

禁止事项：直接降低 `beamSettleMaxTicks`、把长 settle 改短、忽略 Closing/合并/掉落/攻击机会。

阶段目标：settle tick 数或每 tick CPU 至少一项下降 20%，逐 seed 结果一致。

### P5：GC 与 Clone Pool 收尾

目标：降低 `batchGc=841/841/841` 和批次存活堆增长。

实施：

1. 根据 P1 的 Pool miss/容量数据预热，而不是无上限扩大池。
2. 检查 `CloneCandidates` 的 `linkNeighborCellIndices`、队列、special focus 和 normal attack snapshot 是否仍有深拷贝分配。
3. 对固定长度五槽数据继续优先使用 struct/预分配数组，不创建短命 Dictionary/List。
4. 确认 `captureTrace=false` 时不创建 Trace DTO、tickLog、breakdown Dictionary。
5. 在 Unity Profiler 可用时，用 GC Alloc/Managed Heap/GC.Collect marker 复核；`batchManagedDeltaBytes` 仅作辅助。
6. 每项池化后跑多线程重复测试，检查归还后引用、跨 seed 污染和非确定性。

阶段目标：L100×400 的批次 GC 次数下降至少 30%，无 Pool 泄漏或结果漂移。

### P6：可选搜索预算实验，必须独立开关

这一阶段可能改变策略结果，只有 P2–P5 收益不足且用户明确接受时才能执行。

可实验：

- 大盘面动态 `maxDepthSimulations`。
- 更小的 depth shortlist。
- 基于确定上界的 branch-and-bound。
- Temporal top-K 或 delay 集合调整。

要求：默认关闭；独立参数；输出逐 seed 差异、胜率差异和 Replay 差异。不得混入“无语义优化”提交。

## 7. 验收指标

### 7.1 必须通过的正确性

- 固定 20 个样本 seed：所有结果字段完全一致。
- Trace 样本：action 序列、Beam 选择和 Replay 签名一致。
- L100×400：逐 seed 结果一致，不只比较总胜率。
- 1 worker 与 6 workers 逐 seed 一致。
- 同配置重复 3 次无竞态、无异常、无 Pool 污染。
- Unity 重新编译无错误，`git diff --check` 通过。

### 7.2 性能阶段目标

| 指标 | 当前 | 第一目标 | 最终目标 |
|---|---:|---:|---:|
| L100×400 wall | 164.2s | ≤140s | ≤123s（至少提升 25%） |
| runAvg | 2451.9ms | ≤2100ms | ≤1800ms |
| P95 | 2995ms | ≤2600ms | ≤2300ms |
| decisionAvg | 2128.5ms | ≤1800ms | ≤1550ms |
| depth | 1402.9ms | ≤1150ms | ≤950ms |
| temporal | 541.8ms | ≤380ms | ≤300ms |
| batch GC | 841 | ≤650 | ≤500 |
| workerUtil | 99.6% | ≥95% | ≥95% |
| workerWait | 0ms | 接近 0 | 接近 0 |

性能目标是方向性门槛，正确性优先；若结果漂移，即使更快也不能合入无语义优化阶段。

## 8. 每个补丁的执行模板

1. 说明本补丁只优化哪个热点，以及为什么不改变语义。
2. 修改前保存相同配置基线。
3. 使用 `apply_patch` 做最小改动。
4. 运行 `git diff --check`。
5. Unity CLI 执行重新编译并确认 `recompile_status` 无错误。
6. 跑固定 seed 样本，比较逐 seed 结果。
7. 跑 1 worker 与 6 workers 一致性。
8. 跑 L100×400×6，记录 `[BotPerf]` 和 `[BotPerfPhase]`。
9. 记录收益、GC、结果差异；无收益或有漂移则只回退本补丁，不影响用户其他改动。
10. 一次只提交一个可解释的优化点，不把预算调整与池化混在一起。

## 9. 推荐实际顺序

```text
P0 正确性护栏
  -> P1 细分 root/depth/temporal settle 与 Clone 来源
  -> P2 Temporal 无语义优化
  -> P3 Depth 稳定 Top-K + 及时归还
  -> P4 Settle 重复扫描与无变化短路
  -> P5 Pool/GC 收尾
  -> P6 可选预算实验（默认不做）
```

第一优先级不是调线程，而是减少每局的深层模拟成本。当前 6 worker 已经满载且均衡；继续加线程只会放大 GC 和 CPU 争用。

## 10. 临时日志移除条件

只有同时满足以下条件后，才移除 `TEMP-BOT-PERF-LOG`：

- 最终 L100×400 基线已保存。
- 正确性矩阵全部通过。
- 新 Agent 已记录最终热点和收益归因。
- 不再需要比较 root/depth/temporal/settle/worker 指标。

移除后再次执行 Unity 编译、`git diff --check` 和最小 Bot 批跑，确保诊断代码没有遗留依赖。
