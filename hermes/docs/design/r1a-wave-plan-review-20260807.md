# R1a 分波次按需跑方案（v2）审查报告

> 审查人：subagent（只读分析，未改代码）
> 依据源码：`BlastMultiTierPhase1AdaptiveSampler.cs`（592 行）、`BlastMultiTierOptimizer.cs`（4247 行）、`BlastDifficultyApplier.cs` / `BlastDynamicDifficultyPureLogic.cs`（机制）、skill 记忆 `multi-tier-phase1-sampling-redesign-20260807.md` / `multi-tier-phase1-cost-diagnosis-20260807.md` / `phase1-ratios-template-design.md`

## 一、结论摘要

**总体可行，方向正确，与现有架构天然兼容，最小 diff 可落地。** 方案本质是"把旧机制的按需生成思想（R1b/R2 已用）推广到 R1a 的 ratios 轴"，与现有 `R1a→R1b→R2` 骨架不冲突。但有 **3 处必须修正**：

1. **Wave1 候选数是 21，不是 ≈25**：全0 模板只配 sd0（现有逻辑），5 sd × 5 核心 = 5 + 4×4 = **21**；
2. **覆盖检查必须按 (sd, target) 粒度**（该 sd 的 evals 是否覆盖该目标段），不能按 target 全局粒度——否则 normal 关 sd0 一覆盖，所有 sd 的剩余 ratios 全跳过，丢掉整个 sd 轴信息；
3. **核心 5 ratios 建议换集**：原案 {单段前, 双段前, 三段前, 隔段, 全0} 前倾，按模板设计审查结论，5 个单段才是区分度最高的"难度咬点"词汇，建议核心 = 5 单段。

另注意：**节省的最终度量要含 extension 补偿**（phase1 软填充不满足时 extension ≤40 会自动补），真实收益以"总 phase1 样本数 + 耗时"为准。

## 二、现状代码结构核对（已逐行验证）

### phase1 调用流程（optimizer L745-975）
```
baseline(1) → R1a 全量 71（BuildRound1Plans, 一次跑完）
  → focusTargets = CollectUnsatisfiedConfiguredTargetWinRates（distinct 目标，降序）
  → R1b while 循环（BuildRound1BinaryFillPlans，≤16，每批评估后带更新 evals 重调，深度 5）
  → R2（BuildRound2NeighborhoodPlans，剩余预算，每目标 1 seed × 4）
  → 硬门 TryValidatePhase1HardMinimum（每档 ≥1 个 overlap-gate 通过候选，不过则整关 STOP，extension 前）
  → extension 软填充（每档 ≥3 个 gate 候选，不足则定向补 ≤40）
```
- `sampleSoftCap = phase1Samples = 100`；R1a 预算 = `min(71, remaining - 16)`（**R1b 保 16 下限**）；R2 现状只能拿到 `100-1-71-16 = 12`
- R1a 评估循环（L792-838）本身**已经是"逐候选评估、边跑边积累 allPhase1Evals"**——拆 Wave1/Wave2 只需把循环体跑两遍，中间插覆盖检查，**结构性零改动**
- `phase1AdaptiveMandatoryEvals` 是只 add 不读的死列表，不影响
- `RunPhase1MandatorySample` 内部 `ResolveUniquePhase1MandatoryCandidate` + `seenKeys` 双保险去重

### sampler 关键事实
- `BuildRound1Plans(config, count, seenKeys)`：sd 主序 `sdOrder=[0,40,10,30,20]` × 全 15 preset，全0 仅 sdIndex==0 发射，count 截断，of 随 sd `{0,.25,.5,.75,1}`
- `CountSamplesInBand(evals, target, margin)`：**private static，无 sd 过滤**，统计 [target±margin] 内 evals 数；R1b 用它做"带内有样本→跳过该目标"
- R1b：`CountSamplesInBand>0 → continue`（按需）；二分 bracket 取排序曲线相邻对；sd 撞钳制时转 ratios/of 变体
- R2：`SelectNeighborhoodSeed` 带内最优 seed（无带内则最近任意），沿 sd 方向 ±2 步加密

### 关键机制（自适应成立的前提，已核实源码）
```
index = max(0, difficultyLevel) × levelDifficultyFactor + startDifficulty
numToShuffle = ceil(max(0,index)/100 × size)
```
- **normal（difficultyLevel=0）**：sd=0 → index=0 → numToShuffle=0 → 完全不洗牌 → 该 sd 下 15 个 ratios 行为等价（实测 L110 sd=0 的 15 候选 wr 全挤 57~60%）；但 normal 的 sd=10/20/30/40 仍洗牌（index=sd）
- **hard/superhard（difficultyLevel>0）**：即使 sd=0 也洗牌（index>0）→ ratios 有区分度
- 全0 ratios：`sum<=0` 无条件零洗牌，与 sd 无关 → 只配 sd0 正确

## 三、三个核心问题的验证

### 3.1 BuildRound1Plans 是否支持"每 sd 子集"？→ **不支持，需加参数（最小 diff）**

现签名 `(config, count, seenKeys)` 内部硬编码全 15 preset × sdOrder。最小 diff 二选一：
- **A（推荐）**：加可选参数 `IReadOnlyList<int> presetIndices = null`；null = 全量（现有调用方零改动），非 null = 只发射这些 preset（全0 只配 sd0、of 映射、count 截断、EnsureUniqueCandidate 逻辑全部复用）
- B：新增 `BuildRound1SupplementPlans(...)`（见修改清单），发射逻辑复制一份

### 3.2 CountSamplesInBand 能否复用？→ **能，加一个可选 sd 过滤**

R1b 的按需判断用的就是它（"带内>0 跳过"），语义完全一致。Wave2 需要"**该 sd** 是否覆盖该 target"：
- 最小 diff：`CountSamplesInBand` 加可选参 `int? startDifficulty = null`（private 方法，改签名即可）；或调用方先 `evals.Where(e => e.candidate.startDifficulty == sd)` 再调（零 sampler 改动）
- ⚠️ 带宽语义核对：`CountSamplesInBand` 用 ±15pp（phase1WinRateMargin）；硬门 gate 是 `overlapGap = max(0,|μ−t|−Z·std) ≤ 8pp && rawGap ≤ 15pp`。100 局时 CI 半宽 ≈ 8pp → gate 实际 ≈ ±16pp，**比 ±15pp 带宽更宽** → 带内覆盖基本等价 gate 通过，硬停风险增量很小（见风险 5.3）

### 3.3 Wave2 与 R1b 冲突？→ **不冲突，正交**

| 维度 | Wave2 | R1b |
|---|---|---|
| 探索轴 | ratios 轴（固定 5 刻度 sd） | sd 轴（WR 曲线二分插值） |
| 触发条件 | 该 (sd,target) 带内无样本 | 该 target 带内无样本（全局）且有 bracket |
| 预算 | Wave2 预算（剩余−16） | 保底 16，互不侵占 |

- 去重双保险（构建期 `EnsureUniqueCandidate` + 评估期 `ResolveUniquePhase1MandatoryCandidate`），不会跑重复 sim
- Wave2 先跑 → 带内样本变多 → R1b 的跳过条件更易命中 → R1b 花得更少，预算自然流向 R2
- Wave2 补充候选让 R1b 的排序曲线更密，bracket 解析质量更高
- 唯一理论重叠：R1b 的 sd-clamped 分支 ratios±1 扰动可能接近某 preset 形状，但 key 不同仍各跑一次（1-2 次 sim，可忽略）
- **顺序建议：Wave1 → Wave2 → R1b → R2（R1b 位置不动，零额外 diff）**。不建议把 R1b 挪到 Wave1 后：R1b 的 mid-sd（5/15/25/35）不在 5 刻度上，按刻度 sd 过滤的覆盖检查不认它们，收益有限

### 3.4 normal/hard 自适应？→ **机制成立，纯数据驱动，无需显式难度分支**

- normal：sd0 零洗牌 → Wave1 的 sd0 核心全落同一 band → 覆盖 → Wave2 跳过 sd0 剩余 10 个 → **自动省**
- hard：sd0 也洗牌 → Wave1 核心分散 → 更多 (sd,target) 未覆盖 → Wave2 自动补 → **自动保留**
- 这比 cost-diagnosis 里"按难度硬编码裁剪"的方向更优（不用查 difficultyLevel，靠覆盖数据自适应），**前提就是 3.2 的 (sd,target) 粒度**

## 四、方案优点

1. **不降质量的结构性保证**：未覆盖 (sd,target) 对 → Wave2 补全剩余 ratios → 与全跑的覆盖矩阵一致；只砍"带内已有样本"的冗余形状
2. **预算自然重分配**：R2 下限从 12 提到 ≥16（Wave2 顶格 46 时：100−1−21−46−16=16），加密预算只多不少
3. **自适应难度**：无需读 difficultyLevel，覆盖数据自动区分 normal/hard
4. **最小 diff**：sampler 加参数 + optimizer 拆循环，R1b/R2/闸门/extension 全不动
5. 与现有 R1b 模式同构（"sampler 生成计划 → optimizer 执行"），架构一致性好

## 五、漏洞与风险

### 5.1 算术误差（方案数字需修正）
- Wave1 = **21** 不是 ≈25（全0 只配 sd0 → 5+4×4）
- 每个覆盖对的节省是 **10**（15−5）不是 14
- "75→40-55" 量级合理但偏乐观：normal 3 目标（85/65/50）典型场景 ≈ 21+10（sd0 补 85）+少量 = **35-50**；hard 5 目标 Wave2 可能顶格 46 → 总 68+16+16=100，**几乎不省**（但不更差）

### 5.2 核心 5 ratios 前倾（最大设计漏洞）
- 原案 {10,0,0,0,0}/{10,10,0,0,0}/{10,10,10,0,0}/{10,0,0,0,10}/全0 = **前段/前段/前段/首尾/全0**，后段、中段形状全不在核心
- 后果 A（已覆盖对的质量损失）：某 (sd,target) 被核心覆盖 → Wave2 跳过 → 若真正的更优形状是后段型（如 {0,0,0,10,10}），phase2/3/final 只能在次优形状里选。sd 是胜率骨架、ratios 是二阶形状，损失有界但真实存在
- 后果 B（hard 关节省打折扣）：前倾核心在 hard 关命中带概率低 → Wave2 触发多 → 省得少
- **建议**：核心 5 换 **5 单段** `{10,0,0,0,0} {0,10,0,0,0} {0,0,10,0,0} {0,0,0,10,0} {0,0,0,0,10}`——模板设计审查结论"单段区分度最高、最直观，是定位难度咬在哪的核心词汇"；全0 移入 sd0 的补充集（normal 下与单段等价不跑，hard 下需要时自动补）。退而求其次可保留原案，但至少补一个后段代表

### 5.3 硬停闸门 delta 风险（低）
- 硬门（L988，extension 前）要求每档 ≥1 个 gate 候选，不过则整关 STOP
- Wave2 覆盖判据（±15pp 带宽）与 gate（≈±16pp @100 局）基本等价，带内覆盖 → gate 通过的对应关系成立；且带内候选数从 15→5（normal sd0）仍 ≥ 软填充 3，extension 不触发
- 残余风险集中在"带宽覆盖但 gate 不通过"的窄带（目标恰在带宽边缘 + 后验窄）——与全跑方案同类风险，非新引入；可接受

### 5.4 extension 补偿会吃掉部分节省
- 软填充（每档 ≥3 gate 候选）不满足 → extension ≤40 定向补。Wave2 只保证"带内 ≥1"，不保证每档 ≥3 gate 候选 → hard 关可能触发 extension
- **验收指标必须用总样本 = mandatory + extension**，别只看 R1a 段

### 5.5 normal 关 sd0 对不可达目标的无效补充（与现状持平，可选优化）
- normal 关 sd0 永不洗牌 → 85% 类目标在 sd0 任何 ratios 都不可达 → Wave2 仍会为 (sd0,85) 补 10 个注定无效的候选（全落 57-60%）。与全跑现状相同（不更差），但可加 3 行难度感知短路：`config.difficultyLevel == 0` 时跳过 sd0 的 Wave2 补充（机制上安全：index=0 → numToShuffle=0 与 ratios 无关）。**可选，非必须**

### 5.6 预算分配（已验证无挤占）
- Wave2 上限 = `remaining − 16`（R1b 保底不动）；R1b 16 保底、R2 ≥16、extension 40 独立，全部不越界

## 六、落地修改清单（最小 diff，2 文件）

**文件 A：`BlastMultiTierPhase1AdaptiveSampler.cs`**

1. 新增常量：
```csharp
/// <summary>Wave1 核心 ratios（按玩法意图选：5 单段 = 难度咬点词汇；全0 由补充集覆盖）。</summary>
internal static readonly int[] Round1CorePresetIndices = {0, 1, 2, 3, 4};
```
2. `BuildRound1Plans` 加可选参数（null = 全量，向后兼容）：
```csharp
internal static List<Phase1AdaptivePlan> BuildRound1Plans(
    MultiTierConfig config, int count, ISet<string> seenKeys,
    IReadOnlyList<int> presetIndices = null)
// 内层循环 for ri 改为遍历 (presetIndices ?? 全量索引)；全0 仅 sdIndex==0、of 映射、count 截断、unique 处理全复用
```
3. `CountSamplesInBand` 加可选过滤：
```csharp
private static int CountSamplesInBand(IList<CandidateEvaluation> evals, float target, float margin,
    int? startDifficulty = null)
// 过滤条件：startDifficulty == null || eval.candidate.startDifficulty == startDifficulty.Value
```
4. **（推荐）新增 Wave2 计划生成**（仿 R1b 的"生成计划"模式，最内聚）：
```csharp
/// <summary>R1a Wave2：对 (sd,target) 带内无样本的对，补发该 sd 剩余 ratios（每对最多 10）。
/// 调用方在 Wave1 评估后带更新 evals 调用一次。</summary>
internal static List<Phase1AdaptivePlan> BuildRound1SupplementPlans(
    MultiTierConfig config, IList<float> focusConfiguredTargets, IList<CandidateEvaluation> curveEvals,
    float margin, ISet<string> seenKeys, int remainingGlobalCap)
// 伪代码：
//   for target in focusTargets（降序，与 R1b 一致）:
//     for sdIndex in sdOrder（与 BuildRound1Plans 一致 [0,4,1,3,2]）:
//       sd = Round1SdScale[sdIndex]
//       if CountSamplesInBand(curveEvals, target, margin, sd) > 0: continue   // 该 sd 已覆盖
//       for ri in 剩余 preset（全量 15 − 核心 5，即 {5..14}；全0 仅 sd0 且已在核心 → 自然跳过）:
//         发射 CreateFixedCandidate + of + EnsureUniqueCandidate（逻辑与 BuildRound1Plans 完全一致）
//         预算 remainingGlobalCap 截断
```

**文件 B：`BlastMultiTierOptimizer.cs`（L786-838 区域）**

5. R1a 段改三段式（**R1b/R2 及以下代码零改动**）：
```csharp
// Wave1：核心集
var wave1Count = Mathf.Min(Round1CorePresetIndices.Length
    + (Round1SdCount - 1) * (Round1CorePresetIndices.Length - 1),   // = 21
    Mathf.Max(0, sampleSoftCap - phase1SampleIndex - Round1BinaryFillGlobalCap));
var wave1Plans = BuildRound1Plans(_config, wave1Count, phase1PlanningSeenKeys,
    BlastMultiTierPhase1AdaptiveSampler.Round1CorePresetIndices);
// ...现有评估循环体原样跑 wave1Plans...

// focusTargets 提前到这里（原 L839）
var focusTargets = CollectUnsatisfiedConfiguredTargetWinRates(_config.tiers);

// Wave2：按需补（预算 = 剩余 − R1b 保底）
var wave2Budget = Mathf.Max(0, sampleSoftCap - phase1SampleIndex
    - BlastMultiTierPhase1AdaptiveSampler.Round1BinaryFillGlobalCap);
var supplementPlans = BuildRound1SupplementPlans(_config, focusTargets, allPhase1Evals,
    _config.phase1WinRateMargin, phase1PlanningSeenKeys, wave2Budget);
// ...同一评估循环体跑 supplementPlans（targetLabel 标注 "round1 wave2 sd=.. preset ../15" 便于日志核对）...
```
6. 评估循环体抽局部方法或复制一份（~15 行），`phase1SeenKeys`/`phase1PlanningSeenKeys`/`phase1SampleIndex` 沿用
7. （可选）`config.difficultyLevel == 0` 时跳过 sd=0 的补充（5.5）

**明确不做**：不动 R1b 深度/预算、不动 R2、不动闸门、不引入显式难度分支、不改 phase1Samples 语义。

## 七、验证方案（落地后）

1. **静态先行**：batchmode 编译验证（`-batchmode -quit`）——skill 记录当前代码尚未编译验证，先补这个
2. **normal 对照**（如 L110）：改前 vs 改后各跑一轮，对比 phase1 候选数（phase1_raw.csv 行数）、耗时、覆盖矩阵（phase1_reachability.csv）、最终选档结果——**要求覆盖矩阵与选档无回归**
3. **hard/superhard 对照**：验证 Wave2 确实触发（日志 wave2 行数 >0）、总样本（mandatory+extension）与全跑对比
4. **验收指标**：总 phase1 样本数（含 extension）+ 耗时 + 覆盖矩阵 + 最终选档，四者并看
