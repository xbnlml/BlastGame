# Final 选档方案评审：贪心降序 vs 逆序贪心 vs 整体重排 vs 联合优化（DP/枚举）

> 评审对象：`BlastMultiTierOptimizer.cs` `BuildFinalResultsFromCommonPool`（L1532-1687，公共 pool 逐档独立选档）
> 需求：选档时就注意档位差；不设硬性档差阈值；不降性能。
> 评审结论：**贪心（任何方向）都治不了塌缩——塌缩的根因是目标函数里没有 gap，不是选择顺序。推荐联合优化（DP/枚举）把「贴档 + 软 gap」合进一个目标函数，池子只有 ~10-25 条，开销可忽略。**

---

## 一、现状与问题定位

- 公共池 = phase0 + phase3（precision 过滤、按 config key 去重），约 10-25 条。
- 每档独立：`FinalHardGate`（|mean−target|≤10pp 且 std≤阈值）→ compositeScore 降序 → 去重 → 取 top。
- **全链路无任何跨档约束**：可能倒挂、可能塌缩（T3 下探到 62、T4 上探到 61，gap=1pp 也算"通过"）。

关键：塌缩不是"顺序错了"，而是**逐档独立的目标函数里根本没有档差项**。两档各自"最贴目标"时，只要池子里 50% 段没有候选，T4 就会被迫选 61% 的上探值——任何把"每档独立选最近"当目标的算法都会这么做。

---

## 二、候选方案对比

| 方案 | 复杂度（P≈25, D=5） | 修倒挂 | 修塌缩(gap) | 全局最优 | 主要问题 |
|---|---|---|---|---|---|
| **现状**（逐档独立） | O(D·P log P) ≈ 625 | ✗ | ✗ | — | 无跨档约束 |
| **贪心降序**（每档在 WR≤上一档已选值的子池选最近目标） | O(D·P) ≈ 125 | ✅ 构造保证 | **✗ 治不了** | ✗ | 见下 |
| **逆序贪心**（从最低目标开始，反向约束 WR≥上一档） | O(D·P) ≈ 125 | ✅ | ✗ 同降序 | ✗ | 镜像风险 |
| **整体重排**（先独立选，再按 WR 降序重排+微调） | O(D·P) + 排序 ≈ 现状 | ✅ | 微调后部分 | ✗ | 破坏贴档亲和性 |
| **联合优化（DP）** | **O(D·P²) ≈ 3k** | ✅ 构造保证 | ✅ 软目标最优 | ✅ | 需小改结构 |

**复杂度结论：全部方案在"微秒级"同量级，DP 也只是 ~3k 次浮点比较。当前热路径是 O(D·P) 的 clone+gate（所有方案共享），选档策略本身的增量开销可忽略，不降性能要求全部满足。**

---

## 三、逐项分析

### 3.1 贪心降序（候选方案）

- **正确性**：单调递减由构造保证（每档 WR≤上一档已选值）。配置不绑定档位、按 key 去重后自然不同 config。
- **复杂度**：O(D·P)，加一次按 WR 排序 O(P log P)。与现状同量级。
- **致命缺陷（回答用户核心问题）**：**它只修倒挂，不修塌缩**。约束是"WR≤上一档"，只禁止 T4>T3，**不禁止 T4=T3−0.5pp**。用户投诉的 T3 下探/T4 上探场景里，T3=62、T4=61（gap=1pp）完全满足"≤上一档"——塌缩原样保留。因为目标是"最接近本档目标"，gap 不进入目标函数。
- **次优性**：无回溯。T1 选了"对它最好"的配置，可能烧掉唯一适合 T2 的候选，级联饿死下游档；局部最优 ≠ 全局最优。
- **级联饿死**：高目标先选会把"低 WR 稀缺资源"先消耗掉（每选一次既删一个配置、又给后续所有档降低天花板），低档候选本来就稀疏（normal 低档 verified 数据普遍缺、物理下限 p50≈42%），更容易在 T4/T5 断料。

### 3.2 逆序贪心

- 复杂度相同，单调由构造保证（WR≥上一档）。
- 对"低档稀缺"不对称更鲁棒：先锁定稀缺的低 WR 资源，高档 WR 普遍富余（多数配置能到 60-90%），"地板"约束很少真的咬合。
- **镜像风险**：若最低档目标物理不可达（如目标 12.5% 而池底 42%），T5 会选 45% 这种"离目标最近"的值，把地板抬到 45%，T4（目标 20%）被迫 ≥45% → **T4-T5 gap=0 塌缩**。这是物理约束，任何算法都救不了，只能显式标记。
- **结论**：逆序在统计上比降序稳（稀缺端先锁），但**同样的病**——目标里没 gap，塌缩照旧。

### 3.3 整体重排（先独立选→按 WR 降序重排→微调）

- **可行性**：技术上完全可行，diff 最小——独立选档代码不动，加一个排序 + 重映射 + 微调循环即可。
- **它做了什么**：排序保证单调（排序本身就是单调的），**只修倒挂，不创造 gap**。排序后相邻两档可以是 [72, 68, 67, 66, 40]，gap=1pp 照样塌缩。
- **代价（关键缺陷）**：重排丢弃了每档的"贴档亲和性"。独立选时每档配置是为自己目标优化的；重排后配置被换位，可能离新档目标很远。示例：独立选出 84/83/82/78/76（目标 85/80/65/50/40，池子缺低段），排序后 82→T3（离 65 差 17pp）、76→T5（离 40 差 36pp）——纯重排就是垃圾。要救就得"微调"：在单调约束内重新选档，而**微调循环本质就是贪心**。
- **结论**：整体重排 ⊂ 贪心（重排 = 排序 + 一次贪心式修复），质量不优于贪心，只是实现最简单。它能当"最小 diff 的过渡方案"，但治不了塌缩（微调目标若无 gap 项，塌缩依旧）。

### 3.4 联合优化（DP / 有界枚举）——推荐

- **核心思想**：把 5 档看成一个组合一起选，目标函数 = Σ 贴档软分(target_pen) + Σ 档差软分(gap_score)，**单调是硬约束（基本不变量，不是档差阈值）、档差是软目标（无硬阈值）**。
- **DP 构造**：池子按 WR 降序排成 S；档按目标降序处理；dp[t][prevIdx] = 给档 t..D-1 分配 S 中下标 ≥ prevIdx+1 的配置的最小代价。转移时同时知道"本档所选 j"和"上一档所选 prevIdx"，**贴档分和 gap 分在同一点都能算**。下标严格递增 ⇒ 单调 + 不同 config 双保证。复杂度 **O(D·P²)**（D=5、P=25 ⇒ ~3k 次运算）。
- **为什么它修塌缩**：目标函数里有 gap 项。用户场景（T3 目标 65、T4 目标 50，池里 62/61/60 附近）：组合 (T3=62, T4=61) 的 gap_score(1pp) 重罚，组合 (T3=70, T4=58) 的 gap_score(12pp) 达标还拿富余奖励——DP 自动选后者（池里有料时）。池里只有 62/61/60 时，DP 也只能给 (62, 60)，但这是**物理无料**，正确行为是标记而不是静默通过。
- **与现有 Python 工具对齐**：`find_best_monotonic`（tools/find_best_combo.py）已经是这个语义的枚举版（单调剪枝 + `_gap_score` 软分 + `target_pen_seg`），团队已信任它。C# 侧移植 DP 语义 = 消除工具链漂移（skill 里反复出现过 pool.py 与 C# gap 分不一致的坑）。
- **为什么不用枚举**：P≈25、D≤5 时枚举最坏 O(25⁵)≈1e7 但单调剪枝后实际极小，Unity Editor 里也只是个位数毫秒。DP 有多项式上界、实现几乎等价，故以 DP 为准，枚举作为等价可选实现。

---

## 四、池子候选不足时的降级策略（不导致整体失败）

按以下阶梯，**逐档降级、不整体失败**（现状的 per-objective `HasFailedTiers` + `BuildFailedTierEvaluation` 机制保留）：

1. **单调永不放宽**（它是基本不变量，不是档差阈值；倒挂任何时候都错）。
2. **档差永远软**：gap 只进目标函数，永不硬拒——这就是"不设硬性档差阈值"的落地。硬档差规则（gap<5% 判 fail）留在判定层 judge_level.py，选档层不做。
3. **贴档门逐档放宽**：先 10pp 硬门（现状）→ 无解时放宽到 15pp → 再不行去掉硬门只靠 target_pen 软分。每档独立放宽，别整组重来。
4. **DP 的天然降级**：DP 求的是最小代价分配，即使有档进不了门，也会给出"整体代价最小"的组合；结束后对**超出硬门的档单独标记**（reason 区分：`物理不可达`（池底/池顶不够，→ 改目标/改关卡） vs `verified 候选缺口`（→ 补探针+bot）），其余档照常入库。绝不静默输出无料组合。
5. **多 rank 输出保留**：rank0 = 联合最优组合；rank>0 保持逐档 next-best 后备（标注后备，不做联合保证），对齐现状 outputCount 语义。
6. **最可能失败的是最低档**（normal 物理下限高）：允许 DP 输出"可达最优"（可能超目标），但必须带标记+原因，由上层判定，不让优化器静默放行。

---

## 五、性能评估（相对现状）

| 方案 | 增量开销 | 结论 |
|---|---|---|
| 贪心（任意方向） | 约 0（O(D·P)→O(D·P)） | ✅ |
| 整体重排 | 排序 O(D log D) + 微调 O(D·P) | ✅ |
| **DP 联合优化** | **O(D·P²) ≈ 3k 浮点比较**，<0.1ms | ✅ |
| 热路径（clone+gate，所有方案共享） | O(D·P)，不变 | ✅ |

- 选档在管线里只跑一次、池子 25 条以内，任何方案的选档开销都远小于一次 bot 模拟（成百上千局）。"不降性能"对全部方案成立，DP 也不例外。
- 唯一要留意的：DP 前的按 WR 排序建议用 `PosteriorMean` 主键 + `posteriorStd` 破平（近邻均值噪声不误排）；贴档/gap 分用该档目标实时算，不需要额外 clone。

---

## 六、推荐方案

**联合优化（DP over WR 降序去重池）+ 软目标（target_pen + gap_score）+ 硬单调 + 逐档降级。**
理由一句话：池子这么小，贪心省下的时间毫无价值，而贪心/重排恰好在你最关心的"池子缺料"场景里失效——联合优化在这个场景里才显优势，且与既有 Python 工具语义一致。

---

## 七、伪代码（C# 风格，对齐现有结构）

```csharp
// —— 新增 helper（3 个，纯函数）——
float TargetPenSeg(float d) {          // 贴档软分：绿1/黄3/红8（对齐 find_best_combo）
    if (d <= 10f) return 1f * d;
    if (d <= 15f) return 10f + 3f * (d - 10f);
    return 25f + 8f * (d - 15f);
}
float GapScore(float wrHi, float wrLo, float okLo, float nearLo) { // 档差软分，无硬拒（对齐 _gap_score）
    float g = wrHi - wrLo;
    float s = 0f;
    if (g < nearLo)      s += (okLo - g) * 5f + (nearLo - g) * 10f;
    else if (g < okLo)   s += (okLo - g) * 5f;
    else                 s -= Mathf.Min(g - okLo, 35f - okLo) * 0.5f;   // 富余奖励
    if (g > 40f)         s += (g - 40f) * 3f;
    return s;
}
void ComputeTierGapRequirement(float tHi, float tLo, out float okLo, out float nearLo) {
    okLo = tHi - tLo;                  // 目标间距 = 达标线（自洽，无法同时满足时靠软分取舍）
    nearLo = okLo * 0.7f;
    if (okLo < 5f) { okLo = 5f; nearLo = 3.5f; }   // 兜底：目标间距过小时不强行 0 间距
}

// —— 改造 BuildFinalResultsFromCommonPool ——
// 1) 公共池（原样）→ 去重 → 按 PosteriorMean 降序 + posteriorStd 破平，得 S[0..P-1]
var pool = BuildCommonFinalPool(phase0Pool, phase3ByDistinct);
var S = DedupFinalPoolByCandidateKey(pool)
        .OrderByDescending(e => PosteriorMean(e)).ThenBy(e => e.posteriorStd).ToList();
int P = S.Count, D = distinctObjectives.Count;      // Normal D=3，Hard/SH D=5

// 2) 预计算每档目标与档差基准（每档一次，避免内层重算）
float[] tgt = new float[D], okLo = new float[D], nearLo = new float[D];
for (int t = 0; t < D; t++) {
    tgt[t] = ResolveConfiguredTargetWinRate(distinctObjectives[t]);
    ComputeTierGapRequirement(t < D-1 ? tgt[t] : tgt[t-1], t < D-1 ? tgt[t+1] : tgt[t],
                              out okLo[t], out nearLo[t]);
}

// 3) DP：dp[t][prev] = 档 t..D-1 在「prev 为上一档所选下标」下的最小代价
//    prev ∈ [-1, P-1]（-1 = 无上档）；下标严格递增 ⇒ 单调 + 不同配置双保证
const float INF = 1e18f;
float[,] dp = new float[D+1, P+1];
int[,]  bk = new int[D, P+1];
for (int prev = 0; prev <= P; prev++) dp[D, prev] = 0f;
for (int t = D-1; t >= 0; t--) {
    for (int prev = P-1; prev >= -1; prev--) {
        float best = INF; int bestI = -1;
        for (int i = prev + 1; i < P; i++) {          // 必须严格在上一档之后
            float wr = PosteriorMean(S[i]);
            float cost = TargetPenSeg(Mathf.Abs(wr - tgt[t]));
            if (prev >= 0)                             // 与上一档的 gap（此刻两值都已知）
                cost += GapScore(PosteriorMean(S[prev]), wr, okLo[t-1], nearLo[t-1]);
            cost += dp[t+1, i+1];                      // 下一档从其 i+1 起选（gap 在下一层再算）
            if (cost < best) { best = cost; bestI = i; }
        }
        dp[t, prev+1] = best; bk[t, prev+1] = bestI;
    }
}

// 4) 回溯得 rank0 组合（按目标降序每档一个配置）
if (dp[0, 0] < INF) {
    int prev = -1;
    for (int t = 0; t < D; t++) {
        int i = bk[t, prev+1]; if (i < 0) break;
        var e = CloneEvaluationForTarget(S[i], distinctObjectives[t].target);
        UpdateCompositeScore(e, tgt[t]);
        e.outOfTargetMargin = Mathf.Abs(PosteriorMean(S[i]) - tgt[t]) > FinalHardGap; // 超硬门逐档标记
        results.Add(e);   // Normal 按 objective 展开 T1=T2 / T4=T5（原逻辑）
        prev = i;
    }
    // 5) 逐档超硬门检查：仅在「候选不足」时降级——
    //    - 放宽 FinalHardGate 到 15pp 重试（soft 分不变）
    //    - 仍失败 → 该档 BuildFailedTierEvaluation(reason)，reason 区分物理不可达/候选缺口
    //    - 其余档照常返回，不整体失败（HasFailedTiers 逐档置位，对齐现状）
} else {
    // 6) 无任何单调可行组合（罕见：池子全乱序/档位目标间距异常）→ 显式失败，不静默输出
}

// rank>0：保持逐档 next-best 后备（不做联合保证，标注后备），对齐 outputCount 语义
```

**要点**：贴档分和 gap 分都在"两相邻档所选都已知"的转移点计算，DP 结构天然支持；单调与配置互异由下标递增自动保证；FinalHardGate 由"硬过滤器"降级为"标记器"，硬规则留给判定层。
