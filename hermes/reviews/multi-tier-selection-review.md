# BlastGame 多档位优化器 phase2→phase3→final 选档逻辑审查与优化方案

> 审查对象：`Assets/GameModule/Editor/Bot/BlastMultiTierOptimizer.cs`（4194 行，Unity C#）
> 参考标准算法：`tools/find_best_combo.py` 的 `find_best_monotonic` / `_gap_score` / `target_pen_seg` / `_bucket`
> 结论：**P0 必须改（final 无跨档单调+gap 校验）；P1 建议改（phase2 链路不足）；P2 改选择标准（不建议扩候选数）；P3 合并不改。**

---

## 一、现状核对（带行号）

| 环节 | 代码位置 | 现状 |
|---|---|---|
| phase1 | `allPhase1Evals`（747-977） | 广采样（5sd×15ratios），按 winRate 降序 |
| phase2 选候选 | `SelectTopForTier`（3608-3639） | 对每个 distinct tier 目标，取「过 `CredibleIntervalOverlapGate`(SoftOverlapGap=8pp, Phase1AbsoluteCap=15pp)」中**离目标最近**的 top20 |
| phase2 追加 | 1145-1178 | 逐候选追加 phase2Runs(100)，过 stage gate → `passedCandidates` |
| phase3 advance | 1222-1228 | 从 phase2 通过者取**离目标最近 + compositeScore 降序**的 top3（`phase2AdvancePerTier=3`） |
| phase3 追加 | 1241-1268 | 逐候选追加 phase3Runs(200)，后验 std 精度过滤 |
| final 池 | `BuildCommonFinalPool`（1403-1448）| **phase0 + phase3**（已排除 phase1/2 独有候选） |
| final 选档 | `BuildFinalResultsFromCommonPool`（1533-1667）| **逐档独立**：FinalHardGate(单档 gap≤10pp + std≤阈值) → compositeScore 排序 → 每档取 outputCount 个 |

**核心缺陷确认（P0）**：final 是**逐档独立**选档，`FinalHardGate`（469-482）只校验「该档自己的点估计离该档目标 ≤10pp」，**没有任何跨档校验**。因此：
- 可能选出 T1=73%、T2=85%（**倒挂**，违反单调递减）；
- 或 T1/T2 差 5pp（**gap 不达标**）；
- 且每档只保证自己贴近目标，不保证档间梯度。

**为何现在能跑但结果不达标**：gates 全是一维（单档 vs 单档目标），没有组合层面的二维（跨档单调 + 跨档 gap）约束。

---

## 二、P0（核心）：final 增加「跨档单调 + 档间 gap 达标」联合选档

### 为什么改
final 是**交付档**，五档必须单调递减且档间 gap 达标。当前逐档独立选 = 无组合约束，会产出倒挂/梯度不足的无效组合。这是全链路最实质的缺陷。

### 关键设计决策：gap 基准用「目标间距」而非「WR 分档」

参考 `find_best_combo.py` 第 102-106 行（`_gap_score`）：
```python
if targets is not None:
    ok_target = targets[i] - targets[j]
    if ok_target != ok_lo:
        ok_lo = ok_target          # 用目标间距替换 WR 分档！
        near_lo = int(ok_target * 0.7)
```
**管线里永远有 targets**，所以实际生效的 gap 达标线是**目标间距**（`targets[i]-targets[j]`），WR 分档（20/15/10/6）只是无 targets 时的兜底。目标间距即「设计意图」：比如 T1=85/T2=80（间距 5），要求 gap≥20 是**不可能同时满足**"每档贴近自己目标≤10pp"的（84 和 79 只有 5pp 差）。**用目标间距做 gap 达标线才能自洽**，这也正是 find_best_monotonic 的行为。

> 因此 C# 侧 `ComputeTierGapRequirement` 返回：`ok_lo = targets[i]-targets[j]`，`near_lo = 0.7×ok_lo`（与 python 完全一致）；WR 分档仅作 targets 缺失时的兜底。

### 怎么改（`BuildFinalResultsFromCommonPool` 内，最小 diff）

把「逐档独立 unique 选档」改为「**联合枚举选档**」，复刻 find_best_monotonic 的枚举思路：

1. **保留**逐档 `FinalHardGate` 过滤（每档得到 `passedByTier[t]`，已经是「该档贴近目标≤10pp + std 达标」的候选）。每档候选已带 compositeScore。
2. **限制每档候选数**为 top M（如 12，按 compositeScore），控制枚举规模（池本身很小：phase0 + distinct×3，约 15-25 条）。
3. **联合枚举**（distinctTierCount 层嵌套，含剪枝）：
   - **单调**：`wr[t] ≤ wr[t-1]`（不满足直接剪）；
   - **gap**：`gap = wr[t-1]-wr[t]`，要求 `gap ≥ near_lo(t-1,t)` 且 `gap ≤ 40`（参考 108-120 行硬边界）；
   - **配置不绑定档位**：同一 config 可出现在多档 passed 列表（`CloneEvaluationForTarget` 已支持），联合枚举要求**五档 config key 互异**（`len(set(keys))==5`，参考 201-202 行）。
4. **打分选最优**：`q = Σ target_pen_seg(d_t) + Σ gap_score(wrHi,wrLo,ok_lo,near_lo) + Σ compositeScore`（对齐 find_best 的 `target_score + gap_score + source_score`，见 204-206 行）。取 q 最小组合。
5. **无有效组合 → 显式失败**（`HasFailedTiers`，明确原因「final 无法拼出单调+gap=目标间距的组合」），**绝不静默输出无效档**。
6. **展开**：rank0 = 联合选出的组合；rank>0 保持逐档 next-best 后备（不做 gap 校验，标注为后备，符合现状 outputCount 默认=1 的主档语义）。

新增 3 个极小 helper：
- `ComputeTierGapRequirement(float targetHi, float targetLo, out float okLo, out float nearLo)`
- `TargetPenSeg(float d)`（绿1/黄3/红8，对齐 125-146 行）
- `GapScore(float wrHi, float wrLo, float okLo, float nearLo)`（对齐 62-122 行）

### 影响
- ✅ 修复倒挂：联合枚举硬性 `wr[t]≤wr[t-1]`。
- ✅ 修复 gap 不达标：联合枚举硬性 `gap≥near_lo`，且打分偏好 `gap→ok_lo`（目标间距）。
- ✅ 对齐「配置不绑定档位」：任何 config 可通过任档 gate 被选入任意档。
- ⚠️ 可能让 final 更容易失败（当目标间距过小、无法满足该档贴目标≤10pp 时显式失败而非给无效档）——这是**特性**，把隐性坏组合变成显式信号。
- ⚠️ 枚举规模受 M 限制，O(M^D)，M=12,D=5 约 25 万最坏，但剪枝（单调+gap）后实际远小；池小可接受。也可用动态规划/贪心降复杂度，但最小 diff 先枚举。

---

## 三、P1：phase2 候选要保证「每个目标段都有候选 + 覆盖下探区间」

### 为什么改
`SelectTopForTier`（3608-3639）只取**离目标最近**的 top20。若 phase1 采样在某目标段稀疏，或全部簇在目标附近，则 phase2→phase3→final 的池子**缺少 WR 跨度**，P0 联合选档会因找不到 gap 达标的组合而频繁失败。这是 P0 的**喂料前哨**。

### 怎么改（改 `SelectTopForTier`，最小 diff）
把「严格最近」改为「**窗口 + 分带**」选择：
1. **窗口放宽**：接受 WR ∈ `[target - 下探幅, target + 15pp]` 的候选（下探幅 = 到下一较低目标所需的最大 gap，如 `max(target_t - target_{t+1})`），而非只 `[target]` 附近。
2. **分带覆盖**：把窗口按 WR 切成若干子带（如 3 段：≥target、target 附近、<target），每带至少选 1 个（优先过 gate 的），保证本档候选集**横跨目标邻域**，为 P0 的单调+gap 提供原料。
3. **gate 分级**：「最贴近目标」的核心候选仍走 `CredibleIntervalOverlapGate`(8pp/15pp)；「下探/上探」的 margin 候选走放宽 gate（如 overlap 距离拉大或仅 `.winRate≥5` 硬过滤），确保每个档位有覆盖而不只是最近。

### 影响
- ✅ 保证每个目标段的候选进入 phase2（不会 85% 段无料）。
- ✅ 为 P0 提供跨档 gap 所需的下探/上探候选。
- ⚠️ phase2 局数预算不变（仍 top20 个），只是**候选来源更分散**；若 phase1 本身缺某段，phase1 的 extension 定向补带逻辑（2808-2867）已负责，不在本 PR 范围。

---

## 四、P2：phase3 advance 保持数量、改选择标准

### 为什么改
`advanceCandidates`（1223-1228）取「离目标最近 + compositeScore」的 top3。若这 3 个都簇在目标附近，final 池缺 WR 跨度，P0 依旧难成 gap 组合。

### 怎么改（改 1223-1228 的 LINQ，最小 diff）
**不扩候选数**（扩数 = 直接乘以 phase3 局数预算，`phase2AdvancePerTier` 进 budget 计算，见 581-585），改为**分带选取**：
- 从 phase2 通过者中，按「离目标最近」与「compositeScore」之外，**保证 advanced 集合横跨目标邻域**：至少含
  - 1 个最贴近目标且过 FinalHardGate 的候选（贴档主力）；
  - 1 个 WR **明显低于**目标的候选（下探，供 gap 到下一较低档）；
  - 1 个 WR 稍高于目标或有更好 failDist 的候选。
- 若某带无候选，则退回「最近优先」补齐到 `advanceLimit`。

### 影响
- ✅ 不增 phase3 局数预算（`phase3AppendRuns` 不变）。
- ✅ 每个档的 advanced 集合覆盖目标邻域，直接喂 P0 联合选档。
- ⚠️ 与 P1 同理：若 phase2 已提供跨度，P2 的跨带集合自然成立；二者互补，P2 是 P1 的下游筛选。

---

## 五、对齐标准的核对（已满足项，**不改**）

| 标准 | 现状 | 结论 |
|---|---|---|
| **覆盖只认 verified**（bot/summary/phase0，phase1/2 是探针要验证） | final 池 = phase0 + phase3；phase1/2 独有候选**不会**进 final（`BuildCommonFinalPool` 1403-1448 只收 phase0+phase3） | ✅ 结构上已满足，无需改 |
| **配置不绑定档位** | `CloneEvaluationForTarget` 逐档 re-clone + re-gate，任何 config 可任档 | ✅ 已满足，P0 联合枚举沿用 |
| **target_pen_seg**（绿1/黄3/红8） | final 无此分段罚分（FinalHardGate 已限 d≤10 即全绿） | ⚠️ P0 打分加入 `TargetPenSeg`，虽 final 全绿仅 d 线性项，但与标准对齐 |
| **五档单调 + 档间 gap 分档** | **❌ 完全没有** | ✅ P0 补齐（单调硬约束 + gap 用目标间距） |

**P3（phase3 合并评估）**：按用户明确要求不改，保持现状。

---

## 六、最终改动清单（函数级，最小 diff）

| # | 文件/函数 | 加什么 | 影响 |
|---|---|---|---|
| P0-1 | `ComputeTierGapRequirement`（新 helper） | 由 `targetHi-targetLo` 得 `ok_lo`，`0.7×ok_lo` 得 `near_lo`；targets 缺失回退 WR 分档 20/15/10/6 | gap 达标线自洽 |
| P0-2 | `TargetPenSeg(float d)`（新 helper） | 绿 d≤10 斜率1 / 黄 10-15 斜率3 / 红 >15 斜率8 | 对齐标准罚分 |
| P0-3 | `GapScore(wrHi,wrLo,okLo,nearLo)`（新 helper） | 复刻 `_gap_score`：g<near 重罚、g<ok 中罚、g>ok 富余奖励(≤35)、g>40 罚 | 组合排序对齐 |
| P0-4 | `BuildFinalResultsFromCommonPool`（改） | 逐档独立选 → 保留逐档 FinalHardGate 出 `passedByTier`，再**联合枚举选档**（单调+gap 硬剪 + 打分），无解显式失败，rank0=组合、rank>0=后备 | **核心修复** |
| P1-1 | `SelectTopForTier`（改） | 最近 topN → 窗口+分带覆盖（含下探带），margin 候选放宽 gate | 保证每段候选+WR 跨度 |
| P2-1 | phase3 advance LINQ（1223-1228，改） | 最近 top3 → 分带 top `advanceLimit`（贴档+下探+上探） | 不增预算、喂 P0 |
| 不改 | `BuildCommonFinalPool` / `FinalHardGate` / P3 合并 | — | 保持现状 |

**预算影响**：P0 不改局数；P1 不改 phase2 局数（仍 top20）；P2 不改 phase3 局数（仍 3 档）。三处均为**纯选择逻辑**改动，不破坏现有骨架，可编译（纯 C#、无新依赖）。

---

## 七、风险与边界

1. **P0 可能更频繁失败**：当目标间距过小（如 85/80/75/70/65）且每档硬限 10pp 时，单调+gap(目标间距) 与「贴档≤10pp」可能冲突，导致无解。→ 显式 `HasFailedTiers` 是**正确行为**（比静默给倒挂档强）；如需缓解，可像 find_best 那样允许 gap 在 near_lo 带内（软达标）而非硬要求，但会弱化「gap 达标」。建议先硬要求，数据回看后再调。
2. **枚举复杂度**：M=12、D=5 最坏 O(12^5)，需剪枝（单调+gap 提前剪）。若实测慢，可降 M=8 或改 DP/贪心。
3. **P1/P2 依赖 phase1 覆盖**：若 phase1 某目标段本身无候选，P1/P2 无法凭空造料，需 phase1 extension 补带兜底（已存在）。P1/P2 是确保「有料时能让 P0 用上」。
4. **compositeScore 是档位相关的**：联合枚举里每档候选的 compositeScore 需按该档 target 重算（`UpdateCompositeScore` 已支持），枚举前统一算好，避免 O(D) 次重算。