# 优化器 vs bot400 同配置胜率不一致 — C# 根因（2026-08-12）

> 场景：用户问"同一配置，多档位优化器 summary 和 bot400 批跑胜率差 40-80pp，底层逻辑一致吗？"
> 结论：**策略/引擎/seed/maxSteps 两套完全一致**（都走 `BlastBotRunPolicy.RunSingleBatchParallel*` +
> `CreateSingleRunOptions` + `BuildInitialSimulationTemplate`，ScoringOptVg，seed=gameLevel*1000+50+idx*17）。
> **唯一实质差异 = 测的档位难度**：优化器全程按 neutral(T3) 难度测，bot400 按每档真实难度（ForTierForced）测。

## 一、代码路径（已读源码核实）

### 1. 两套机制共用同一跑局引擎
- BotBatchRunner（`BlastBotBatchRunner.cs`）：`BlastBotRunPolicy.RunSingleBatchParallelWaved` → 模板 `BuildInitialSimulationTemplate(level, options)`
- MultiTierOptimizer（`BlastMultiTierOptimizer.cs`）：`RunSingleBatchParallel` → 模板 `BuildInitialSimulationTemplate(simLevel, options)`
- 引擎内部 `RunSingleInternal` → `CreateInitialSimulation` → `FillQueueForSimulation` → `BuildDifficultyContext(level, options)`

### 2. 档位难度的来源 = 队列生成时读哪个 DynamicDifficultyConfigs 槽位
`BlastBotService.SimulationTail.cs::BuildDifficultyContext`:
```
forcedTier > 0 → BlastDifficultyContextFactory.ForTierForced(level, forcedTier)
                → BuildTierForced → ResolveTierDifficultyConfig(stack, forcedTier) → 读 DynamicDifficultyConfigs[tier-1]
forcedTier == 0 → ForNeutralEstimate(level, neutralTier=3)
                → BuildFromResolvedTier → ResolveTierDifficultyConfig(stack, 3) → 读槽位 3（neutral）
```
- `dynamicTier` 字段只进 BI/Views/replay note，**不参与难度计算**（洗牌参数才决定难度）。
- `ResolveTierDifficultyConfig` = `configs[tier-1]`（startDifficulty/splitCount/ratios/of 全来自该槽位）。

### 3. 关键差异：MultiTierOptimizer 全程不传 forcedDynamicTier
- `RunEvaluation` 的 `forcedDynamicTier` 参数默认 null，**全文件只有 L1769 一处显式传 null**，其余调用全部省略（=null）。
- phase0 逻辑（L1726 遍历 tierCount，`BuildCandidateFromAssetTier(tierNumber)` 逐个取 asset 当前配置）：
  `ApplyCandidateToNeutralTierConfig(simStack, candidate)` **把候选配置写进 neutral 槽位**（`DynamicDifficultyConfigs[neutralIndex] = 候选`），
  然后 `forcedDynamicTier: null` → 模板队列 = **neutral(T3) 难度下、用候选配置生成**。
- 注释明示："Unified protocol: apply candidate to neutral tier"、"asset T{tierNumber} → neutral"。
- **因此优化器测出的"某配置胜率" = 该配置在 neutral(T3) 难度下的胜率，不是该配置在目标档位（T1/T2/T4/T5）真实难度下的胜率。**

### 4. bot400 逐档真实难度
`submit_batch_unity --tiers 1..5` → 每档 `forcedTier=T` → 读 `DynamicDifficultyConfigs[T-1]`（asset 该档完整配置）→ 真实档位难度。

## 二、推论与实证（L93 案例）
- summary T4/T5 = 59.5%（sd5/10,1,1,1,10，src=p0，390局）；bot400 T5 = 17%（同一 sd5 配置）。
- phase0_prior.csv 显示：**T4/T5 的 59.5% 实为 phase0 里 T1 档（当时 asset T1=sd5）的先验**，被复用给 T4/T5 目标
  （`ReusedFromTier` 字段可见）。配置相同，但**测的档位难度不同**（T1 先验在 neutral 难度 = 59.5%；T5 真实档位难度 = 17%）。
- ⚠️ 第二个陷阱：**08-09 批次与 08-11 批次跑时 asset 状态不同**（08-09 时 L93 T1/T2=sd5/T3=sd20/T4/T5=sd20；
  08-11 时已被 write_ddc 改写成 sd30/sd40/sd5）→ 同批次 snapshot 对比（见下）是排查第一步。

## 三、排查方法（教训：用户两次纠正"你到底好没好好看"）
1. **先对比两个批次的 asset 快照**，再谈机制：
   - bot400 批次：`telemetry/bot/<batch>/level-assets/test/<lv>.asset`
   - multi-tier-opt 批次：`telemetry/multi-tier-opt/<batch>/<lv>-<ts>/level-assets/test/<lv>.asset`
   - 用正则抽 `StartDifficulty/ShuffleSplitCount/ShuffleSplitRatios/ShuffleOverflowFactor` 成 5 档列表对比。
2. **读全相关 C# 段**，不要凭片段下结论：phase0 确实遍历 T1-T5（用户纠正点 1）；"neutral" 不是关卡难度等级，是**读槽位 3**。
3. **看 summary.csv 的 SourcePhase（p0/p3）与 phase0_prior.csv 的 ReusedFromTier**：p0 = 现配先验校验（快验，可被跨档复用）；
   p3 = phase3 验证（慢，更可靠）。T4/T5 只有 p0 无 p3 = 危险信号。
4. **同四元组 ≠ 同难度**：同一 sd5 配置在 neutral 槽测 59.5%、在 T5 槽测 17% —— 槽位决定完整难度上下文。

## 四、对入库的含义
- 优化器 summary 的"合格"是按 neutral(T3) 难度评的；入库后 asset 把该配置写到目标档位槽，
  bot400 按该档真实难度测 → 与 summary 差异大是**机制必然**，不是批次噪声。
- 已入库关卡想验证真实达标，必须跑 bot400 逐档（submit_batch_unity --tiers）。
- 判"summary 与 bot 不一致"时，先排除 asset 在两批次间被 write_ddc 改过的因素（快照对比）。
