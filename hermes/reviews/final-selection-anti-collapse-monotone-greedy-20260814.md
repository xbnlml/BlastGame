# FinalSelection 防档位塌缩：单调边界贪心选档（方案评审 + 落地）

> 日期：2026-08-14 ｜ 目标文件：`Assets/GameModule/Editor/Bot/BlastMultiTierOptimizer.cs`（4310 行）
> 审查基线：`hermes/project-state/backup-multitier-20260807/BlastMultiTierOptimizer.cs.modified`（4247 行，
> 与现行结构一致，函数行号偏移 ~63 行；`BuildFinalResultsFromCommonPool` 备份 L1551-1684 ≈ 现行 L1532-1687）
> 关联裁定：`multi-tier-selection-optimization-20260807.md`（用户已否决"gap≥目标间距"硬标准、否决事后单调校验、
> 采纳"配置自由流动"；本次 bug 证明自由流动防不住塌缩，需在选档时加单向边界）

## 一、问题机制（源码确认）

现行 `BuildFinalResultsFromCommonPool`（L1532-1687）对每个 distinct objective **逐档独立**从公共 pool
选"离本档目标最近"的候选（`FinalHardGate` 单档 ±10pp + posteriorStd 门 + `CompareFinalCandidates` 排序 +
`selectionByObjective` 按 objectiveKey 缓存共享）。**全函数无跨档信息**。

塌缩/撞车机制 = 相邻两档各自取"离自己目标最近"，一档往低飘、一档往高飘，在中点撞车：
- normal 85/65/50：T3 门 [55,75]、T5 门 [40,60]，重叠区 [55,60]。池子只有 57/55 时，
  T3→57（|57-65|=8≤10）、T5→55（|55-50|=5≤10），**档间差 2pp 仍 status=ok**。
- hard 60/50/33/20/12.5：门宽 ±10pp 使 T1[50,70] 与 T2[40,60] 重度重叠，无边界时可选出 T1=52/T2=58 倒挂。

## 二、方案评审：『按目标降序贪心 + 单调上界』

### 2.1 能有效防塌缩（核心场景 100% 防住）

- 贪心降序 = 先选高目标档，低目标档的候选池**硬性排除 mean > 前档已选值**的候选。
  → "低档往反方向飘过前档已选值"在结构上不可能；**输出必单调**（wr[T1]≥…≥wr[T5]）。
  这正是用户要的机制：用**单调边界（顺序约束）**代替**硬阈值（距离约束）**，且发生在"找档位时"，非事后校验。
- 与 2026-08-07 两次用户裁定**不冲突**：① 不用 find_best 的 gap≥目标间距（边界是顺序不是距离）；
  ② 不做事后校验（边界在选档即生效）。
- 数据受限场景（池子本身没拉开，如低段只有 33/30）：贪心输出最接近目标的单调组合，与现状同结果——
  **单调边界保证的是"顺序"，不是"间距"**；间距留给数据。这符合"不设硬性阈值"。

### 2.2 引入的新问题与对策

| 风险 | 说明 | 对策 |
|---|---|---|
| 低端候选稀疏 → 窗口内选不满 | normal 低档 verified 稀疏是文档化事实；T3 选了 58 时 T5 窗口收窄为 [40,58] | soft-overflow 降级（见 4.6）：窗口内不足时，从过 gate 但略超边界的候选中按"违例最小"补足；仅主选溢出才违反单调，记 warning 不硬失败 |
| 某档最优配置被前档占用 | 现状允许同一配置被两个 distinct objective 同选（无跨 objective 去重）→ 本身就是塌缩（同 WR） | consumed 集合：每档选出的配置标记占用，跨档不复用。normal T1=T2/T4=T5 组内共享不变（同 objectiveKey） |
| 级联欠射（顺序偏差） | T1 偏低会压缩后续窗口，但每档仍有自己的 ±10pp gate，输出仍贴目标 | 可接受；可选 lookahead-1（见 4.7） |
| normal 共享档 | 必须按 distinct objective 迭代（85→65→50 三段边界链），不能按 5 个配置档 | objectives 按目标 WR 降序收集，T2/T5 由现有第二段展开循环自动共享 |
| 性能 | O(D·P log P)，与现状同级；零新增 bot 局数；新增 1 个 HashSet + 1 个 float | 无风险 |

## 三、方案替代项对比

| 方案 | 防塌缩 | 硬阈值 | 性能 | 结论 |
|---|---|---|---|---|
| **A. 降序贪心 + 单调上界 + soft-overflow**（推荐） | 单调保证 | 无（仅顺序边界，数据不足可松弛并告警） | O(D·P log P)，零新增局数 | ✅ 落地 |
| B. 软分离加分（soft separation bonus） | 数据有余地时额外拉开间距 | 无 | 同 A | 可选开关项，默认关 |
| C. 联合枚举（find_best_monotonic 复刻，O(M^D)） | 全局最优 | 有（gap≥near_lo 硬剪） | O(M^D) 有风险 | ❌ 用户已否决 gap 硬剪 |
| D. lookahead-1 一档回看 | 缓解级联欠射 | 无 | O(D·P)，仅降级时触发 | 可选增强，并入 A 的降级链 |

## 四、具体落地（函数名 + 伪代码）

**改动范围：仅 `BuildFinalResultsFromCommonPool`（现行 L1532-1687）的主选档循环。**
Phase1/2/3 与 `SelectTopForTier` **零改动**（不碰 bot 局数预算；Phase3 时高档最终值未知，无法提前用边界）。

### 4.1 设计决定
1. **边界 = 上一 distinct objective 主选（rank-0）的 PosteriorMean**（不是目标、不是分位数）——用已选值才能保证输出单调。
2. **迭代对象 = distinct objectives 按目标 WR 降序**（`BuildObjectiveKey` 语义，与现有 selectionByObjective 缓存一致；normal = [85,65,50]，3 段边界链）。
3. **boundary 初值 = +∞**（第一档不受限）。
4. **consumed 集合**：每档选出的 perTierCount 个 config key 全部占用，跨档不复用。
5. **FinalHardGate 不变**：单档贴目标 ≤10pp + posteriorStd 门照旧；单调边界只加"上界"，永不放松单档门。
6. **降级 = soft-overflow**：窗口内不足 → 从"过 gate 且未占用但 mean > boundary"的候选中按 (mean−boundary) 升序补足。
   - 补足只影响该档的备用（alternate）时，headline 主选仍单调；
   - 主选也溢出才违反单调 → `tierMonotoneRelaxed=true` + warning，**不设 HasFailedTiers**（数据稀疏 ≠ 硬失败，避免拖慢流水线）；
   - soft-overflow 后仍不足 → 走现有失败路径（failureByObjective / BuildFailedTierEvaluation / HasFailedTiers，含已落地的 best-available 展示），失败分支**原样保留**。
7. **同目标 WR、不同 fail-dist 的 objectives**（罕见）：按 BuildTargetWinRateKey 合并为一组处理（组内允许复用配置，同 normal T1/T2 语义），避免互相抢占。

### 4.2 伪代码（替换 `BuildFinalResultsFromCommonPool` 主循环）

```csharp
// ===== 在函数开头（BuildCommonFinalPool 之后）=====
var pool = BuildCommonFinalPool(phase0Pool, phase3ByDistinct);
var perTierCount = Mathf.Max(1, outputCount);

// 1) 收集 distinct objectives，按目标 WR 降序（normal -> [85,65,50]）
var objectives = new List<(string key, TierTarget target, float configured)>();
var seenObj = new HashSet<string>(StringComparer.Ordinal);
for (var t = 0; t < configuredTiers.Count; t++) {
    var target = configuredTiers[t];
    if (target == null) continue;
    var key = BuildObjectiveKey(target);
    if (seenObj.Add(key))
        objectives.Add((key, target, ResolveConfiguredTargetWinRate(target)));
}
objectives.Sort((a, b) => b.configured.CompareTo(a.configured)); // 降序

var consumed = new HashSet<string>(StringComparer.Ordinal);      // 跨档已占用配置
var boundary = float.PositiveInfinity;                           // 单调上界
var selectionByObjective = new Dictionary<string, List<CandidateEvaluation>>(StringComparer.Ordinal);
var failureByObjective = new Dictionary<string, string>(StringComparer.Ordinal);
var anyFailed = false;

// 2) 贪心主循环（替换原 for tier 0..N 主循环）
foreach (var obj in objectives) {
    var passed = new List<CandidateEvaluation>();
    var overflow = new List<(CandidateEvaluation eval, float over)>();
    for (var i = 0; i < pool.Count; i++) {
        var source = pool[i];
        if (source?.candidate == null) continue;
        var clone = CloneEvaluationForTarget(source, obj.target);
        if (clone == null) continue;
        if (!FinalHardGate(clone, obj.configured)) { clone.outOfTargetMargin = true; continue; }
        if (consumed.Contains(clone.candidate.ToKey())) continue;       // 已被更高档占用
        clone.outOfTargetMargin = false;
        clone.status = "ok";
        UpdateCompositeScore(clone, obj.target);
        var mean = PosteriorMean(clone);
        if (mean <= boundary + 0.0001f) passed.Add(clone);              // 单调窗口内
        else overflow.Add((clone, mean - boundary));                    // 边界外（降级用）
    }
    passed.Sort((a, b) => CompareFinalCandidates(a, b, obj.configured)); // 现有比较器不动
    // 取 unique 前 perTierCount
    var unique = new List<CandidateEvaluation>();
    var seen = new HashSet<string>(StringComparer.Ordinal);
    for (var i = 0; i < passed.Count && unique.Count < perTierCount; i++)
        if (seen.Add(passed[i].candidate.ToKey())) unique.Add(passed[i]);

    // 3) 降级：窗口内不足 -> 按最小单调违例补足（soft overflow，不硬失败）
    if (unique.Count < perTierCount && overflow.Count > 0) {
        overflow.Sort((a, b) => a.over.CompareTo(b.over));
        foreach (var o in overflow) {
            if (unique.Count >= perTierCount) break;
            if (seen.Add(o.eval.candidate.ToKey())) {
                o.eval.tierMonotoneRelaxed = true;
                unique.Add(o.eval);
                Debug.LogWarning("[MultiTierOptimizer] FinalSelection 档 " + obj.target.name
                    + " 单调边界松弛 " + o.over.ToString("P0", CultureInfo.InvariantCulture)
                    + "（窗口内候选不足，soft overflow）");
            }
        }
    }
    if (unique.Count < perTierCount) {                                  // 绝对失败（gate 真空），原样保留
        anyFailed = true;
        var reason = "FinalSelection 目标 " + (obj.target.name ?? obj.key)
                     + " 硬门合格唯一配置仅 " + unique.Count + " 个(需要 " + perTierCount + ")";
        failureByObjective[obj.key] = reason;
        Debug.LogWarning("[MultiTierOptimizer] " + reason);
        continue;
    }
    selectionByObjective[obj.key] = unique;
    foreach (var u in unique) consumed.Add(u.candidate.ToKey());        // 4) 占用配置
    boundary = PosteriorMean(unique[0]);                                // 5) 主选锚定下一档
}

// 6) 第二段展开循环（逐 configuredTier 取 selectionByObjective/failureByObjective）完全不变
```

### 4.3 不变量核对
- **normal 3 有效档**：objectives=[85,65,50]，边界链 85→65→50；85 组选 1 配置 → T1、T2 共享克隆；
  65 → T3；50 → T4、T5 共享。与 `BuildDistinctTierTargets`/Unity dedup 语义一致。
- **hard/superhard 5 档**：5 段边界链；gate 重叠区（T1[50,70]/T2[40,60]）不再可能倒挂/撞车。
- **Phase0 全满足路径**（L732 仅 phase0 池）：同函数受益，零额外成本。
- **失败率不上升**：失败条件 = [过 gate 且未占用] < perTierCount，与现状"过 gate 唯一配置 < perTierCount"
  几乎等价（被占用的都是近塌缩区配置，正是应避免复用的）。
- **性能**：O(D·P log P) 与现状同级；无 bot 局数变化；新增内存可忽略。

### 4.4 落地项清单
1. `BuildFinalResultsFromCommonPool` 主循环改造（上述伪代码）。
2. `CandidateEvaluation` 新增 `tierMonotoneRelaxed`（bool，默认 false）；`ExportFinalCsv` 加列。
3. （可选）方案 B：`CompareFinalCandidates` 增加"距前档已选值 < σ 时软罚"分支，配置开关，默认关。

### 4.5 验证建议（落地后）
- 回归 4 个历史倒挂关（L110/L119/L136/L120）：输出保持单调且不新增失败。
- 构造塌缩数据（池子同段仅 57/55、目标 65/50）：验证输出为 [..,57,48] 或 [..,57,55]，**不是同配置 57/57**。
- 统计 ExportFinalCsv 的 `tierMonotoneRelaxed` 出现率：low-end 稀疏档的高松弛率 = "补探针/改关卡"预警信号。
