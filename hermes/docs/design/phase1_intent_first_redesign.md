# BlastGame phase1 候选生成：从"参数网格"改为"玩法意图/胜率意图"驱动

> 审查对象：`BlastMultiTierPhase1AdaptiveSampler.cs`（532 行）+ `BlastMultiTierOptimizer.cs`（4168 行）
> 本文件先校准机制（源码为准），再评估用户两例，再给落地方案，最后反主 agent 的网格化方案。
> 工作路径：`<BLASTGAME_REPO>`

---

## 0. 先校准机制：四维参数的"玩法效果"到底是什么（源码为准）

在谈设计前，必须把每个参数在游戏里怎么改变牌堆/难度读对，否则意图设计会建立在错觉上。以下是 `BlastDifficultyApplier.cs` / `BlastDifficultyContextFactory.cs` / `BlastDynamicDifficultyPureLogic.cs` 的实读结论：

**sd（startDifficulty）＝难度主轴，单调。**
- `Construct` 里 `difficultyLoopOffset` 直接取 `startDifficulty`（`BlastDifficultyContextFactory.cs:221,234`）。
- `ComputeDifficultyIndex = difficultyLevel × levelDifficultyFactor + difficultyLoopOffset`（`BlastDynamicDifficultyPureLogic.cs:75-77`）。
- `numToShuffle = ceil(index / 100 × size)`（`BlastDifficultyApplier.cs:126`）。

**→ 结论：sd 越高 → 难度指数越高 → 洗牌越多 → 越难 → 胜率越低。** 优化器自己的 `ApplyMandatoryTrackNudge`/`BuildRound2NeighborhoodPlans` 也是这个方向（要更高胜率就 `- sd`）。⚠️ 任务描述里"sd 越低越难"是**反的**，落地时务必以源码方向为准（设计本身只依赖单调性，方向反了只影响符号，不影响结构）。

**sc（shuffleSplitCount）＝把队列按进度切成 N 段。** `SplitGroupsByTargetProgress`，决定各段大小与每段洗牌容量上限（`BlastDifficultyApplier.cs:130-157`）。是次级的"粒度/分布"旋钮，不是难度主轴。

**ratios（各段洗牌权重）＝洗牌在段间的分配。** `AllocateShuffleCounts(total, ratios)`：每段 `≈ total × ratio/sum`。
- **当 `sum == 0`（全 0）→ 直接返回全 0，一段都不洗**（`BlastDifficultyApplier.cs:299-300`）。这是"完全不洗"的最强保证。
- 权重为 0 的段在余数再分配时也被 `RemoveAll(x => x.ratio <= 0)` 剔除（`BlastDifficultyApplier.cs:333`）→ **0 = 该段彻底不参与洗牌**，是"语义上排除"而非"给个 1 还分到一点"。
- 所以 ratios 是"洗牌在空间上铺在哪"的**形状旋钮**，不是难度主轴。

**of（shuffleOverflowFactor）＝二阶"溢出重排"旋钮。**
- 每段能洗的次数被 `cap = 该段组数` 限制（`effective = min(times, cap)`），装不下的算 `overflowTotal`（`BlastDifficultyApplier.cs:150-157`）。
- `of` 只出现在 `overflowConvertedShuffleTimes = overflowTotal × of`（`BlastDifficultyApplier.cs:162-163`），决定溢出的洗牌是否转成跨段重排。
- **→ 只有当"分配到的洗牌次数超过段容量"（即洗得很多）时 of 才有作用。** 洗得少时 `overflowTotal=0`，of 完全无关紧要。

**一句话总结四种旋钮的地位：`sd` 是难度主轴（决定胜率档位），`ratios` 是空间形状（决定洗牌铺在哪/有没有），`sc` 是粒度，`of` 是只有高洗牌时才生效的微调。**

---

## 1. 诊断：当前 phase1 为什么覆盖不全（确认问题）

对照源码，问题与任务描述一致，且比描述的更"叠"：

1. **R1a 的 16 个 ratio preset 全部锁死 sd=20**（`BuildRound1Plans` → `CreateFixedCandidate(..., Round1StartDifficulty=20)`，`BlastMultiTierPhase1AdaptiveSampler.cs:16,112`）。难度轴完全没铺开 → 85% 高难段、50% 低难段一票都没有。
2. **of 锁死 0.5**（`CreateFixedCandidate` 里 `overflowFactor = phase1FixedOverflowFactor = 0.5`，`BlastMultiTierOptimizer.cs:55,311`）。of 从不参与采样。
3. **R2 邻域加密只动 sd（步长 ±2）+ 比率微扰，从不碰 of**（`BuildRound2NeighborhoodPlans`，`BlastMultiTierPhase1AdaptiveSampler.cs:244-272`）。
4. **二分补洞深度仅 2**（`Round1BinaryFillMaxDepthPerSegment=2`，同上:18）。陡峭曲线下 2 个中点可能 50%→80% 跳空，落不进 55-75 band。
5. `EnsureUniqueCandidate` 的去重扰动也只在 `nudge>=4` 才碰 ratios，**从不碰 of**（同上:86-94）。

**根因不是"某一步参数没铺开"，而是整个 phase1 没有"目标胜率段"的概念**：它不care自己服务哪个 band，只是在 sd=20 附近随机折腾 ratios。网格化是把这个盲区"照搬"成三维——仍然不知道哪个格子属于哪个 band。

---

## 2. 对主 agent"ratios × sd × of 三轴网格化"方案的反对意见

**方向对（要铺开三维），但形式错（网格）。** 具体反对：

1. **组合爆炸破预算。** 目标五档（normal 85/85/65/50/50，superhard 50/40/30/20/10，去重约 5 个 distinct）。哪怕很粗的网格：5 sd × 5 ratios × 3 of = **75 格**，还要 R2/extension，直接顶爆 `phase1Samples=100` 软上限，R2/Densify 被截断。而网格还嫌不够——越粗越cover不全，越细越破预算，死结。

2. **网格无视"胜率是有序的"。** wr 有天然序，sd 也有天然序。网格把每个 sd×ratios×of 当独立格子，浪费大量样本在"重新发现同一段单调曲线"。意图设计恰恰相反：**把 sd 当共享的已校准难度轴，ratios/of 只在每个 band 附近做局部形状多样性**。

3. **网格无法把样本倾向难度大的 band。** 85% 高难段曲线陡、难采，需要更密的样本；50% 段平缓、好采。网格对所有 band 一视同仁，无法按难度分配采样预算。意图设计天然能做到"每个目标 band 显式 seed，且给难采的 band 更多 R1b/R2 配额"。

4. **网格的 of∈{0,0.5,1} 是"拍脑袋分层"，不是玩法意图。** 从前面的机制校准看，of 只在"洗牌溢出"时才有效。网格在低 sd（洗得少）的格子里设 of=1 是无效的；在 sd 高的格子里设 of=0 又浪费了它。意图设计只在"确实会溢出"的 band 变 of。

5. **网格治标不治本。** 现在缺 85/65/50 段，是因为"sd 轴没铺开"。网格虽然把 sd 铺开了，但**仍然没有"每个候选属于哪个 band"的意图标注**，phase2 选五档单调 + gap≥15pp 时，还是靠"碰"，不是靠"每个 band 有贴近的候选"这个被保证的前提。

> 一句话：网格是"把三维填满，祈祷命中 band"；意图是"直接对每个 band 撒几发，保证命中，再用 R1b/R2 修正误差"。预算、覆盖、倾向性三者网格全输。

---

## 3. 评估用户的两个例子

### 例1：要洗牌少 → `sd=0, of=0`

**结论：方向对、可采纳为"最易/少洗牌"意图原语，但内部杠杆主次要说清。**

- **主导杠杆是 sd=0**：`numToShuffle = ceil(0/100×size) = 0` → 完全不洗。此时 `overflowTotal=0`，**of=0 是冗余的**（没有溢出可转）。所以 of=0 在这个极端端点"正确但不必要"。
- **真正更稳的"不洗"保证是 ratios 全 0**：`AllocateShuffleCounts` 在 `sum==0` 时**无论 numToShuffle 是多少都返回全 0**（`BlastDifficultyApplier.cs:299-300`）。即：即使 sd 因 min 钳制挪不动，ratios 全 0 也能硬保证不洗。用户"0 比 1 更彻底"的直觉在这里完全成立。
- **落地编码**：作为"最低难/少洗牌"意图原语 → `(sd = 0, ratios = 全 0 或全 1, of = 0)`。sd=0 保证难度指数最小，ratios 全 0 作为兜底保证零洗牌，of=0 作为"连重排都不要"的完成项。三者协同表达"几乎不洗"，方向完全正确。

### 例2：`ratios 1,1,1,1,10 → 0,0,0,0,10`

**结论：完全合理，且是更干净的语义，应采纳。**

- 机制上 `1,1,1,1,10`（sum=14）：前四段各分到 ~7% 洗牌，**还是会被扰动**。
- `0,0,0,0,10`（sum=10）：前四段 `ratio=0` → 在初分配得 0，且在余数再分配时被 `RemoveAll(x=>x.ratio<=0)` **彻底剔除** → 前四段 100% 保持原序，只有最后一段洗。
- **语义差异：`1` 是"以权重 1 参与洗"，`0` 是"该段退出洗牌池"。** 用户说"0 比 1 更彻底"完全正确，且这不是吹毛求疵——它对最终牌堆的扰动分布是真实不同的。
- **落地编码**：把 0-vs-1 变成 ratios 的一个真实语义轴。现有 16 preset 里所有"1,1,1,1,x"类应重写为"0,0,0,0,x"来表达"只洗尾段、其余段保序"的意图；"10,10,1,1,1"类同理可考虑"10,10,0,0,0"。

---

## 4. 意图优先的 phase1 候选生成方案（可落地、不过度设计）

核心思想：**phase1 的候选不是一个"参数格子"，而是一个"胜率意图的编码"。** 每个候选 = `(目标 band, 形状原语, of 档) + 由 band 解出的 sd`。sd 是被"解"出来的共享难度轴，ratios/of 是每个 band 内部的形状多样性，绝不三轴叉乘。

### 4.1 定义形状原语（intent archetypes）—— 一个小的有序意图库

把 ratios/of 收敛成几个有明确玩法语义的原语，而不是随机的格子：

| 意图原语 | ratios 形状 | of | 玩法语义 |
|---|---|---|---|
| `EASY_PLAIN` | 全 1（或全 0） | 0 | 均匀、低频、不溢出重排 → 最高胜率 |
| `EASY_TAIL` | `0,0,0,0,10` | 0.5 | 只洗尾段、其余段保序 → 略高于均匀 |
| `MID_PLAIN` | 全 5 | 0.5 | 均匀中频（接近当前默认） |
| `MID_TAIL` | `0,0,0,0,10` | 1.0 | 尾段重洗 + 溢出重排 → 中档偏难 |
| `HARD_PLAIN` | 全 10 | 0.5 | 均匀高频重洗 |
| `HARD_TAIL` | `0,0,0,0,10` | 1.0 | 尾段极致重洗 + 强溢出重排 → 最低胜率 |

> 这 6 个原语覆盖了"洗牌少↔多"和"均匀↔尾段集中"两个用户关心的维度，且每个都是可名状的玩法意图，不是填格子。**不引入"每个段独立可变"的全叉乘**——那才是过度设计。

### 4.2 R1a：按目标 band 显式播种（替换 16 个锁 sd 的 preset）

对每个 distinct 目标胜率 t（排好序，如 normal 85/65/50，superhard 50/40/30/20/10 去重后取 5 个）：

1. **解出 sd 种子**：用基线锚定。已有 baseline 候选（asset T3 现配）及其实测 `(sd_b, wr_b)`，sd 单调 → 用线性校准估 `sdSeed(t) = clamp(sd_b + round((wr_b − t)/slope))`，slope 默认取 ~5pp/sd（与 `ApplyMandatoryTrackNudge` 的 delta-based 步长一致），或用"baseline + 1 个探针"实测标定 slope 避免魔法常量。**这是"意图 → 参数"的映射，不是枚举。**
2. **在该 sdSeed 上撒 2–3 个形状变体**：取最贴近 t 的 1–2 个原语（t 高 → 选 HARD 系，t 低 → 选 EASY 系，t 中 → 选 MID 系），of 取原语自带值。得到每个 band 2–3 个**彼此不同**的候选（phase2 需要 distinct 配置）。

- 预算：~5 distinct × 2–3 ≈ **10–15 个候选**，替换现在 16 个。**每个 band 由构造保证被 seed**，85% 高难段不可能再缺席。
- `CreateFixedCandidate` 需改：`of` 不再锁 0.5，改为传入原语的 of；`sc` 保持 `phase1FixedShuffleSplitCount`（sc 是粒度旋钮，本方案不铺开它，避免过度设计）。

### 4.3 R1b 二分补洞：加深 + 钳制时切形状（修陡峭跳空）

- 深度上限 `Round1BinaryFillMaxDepthPerSegment` 从 2 → **3~4**（陡峭 85% 段需要更密的中点）。
- 关键修复：当 sd 中点撞到 `startDifficultyMin/Max` 钳制仍无法命中 band 时，**不再死推 sd，而是改在 `ratios/of` 上切变体**（sd 已饱和，剩下的杠杆只剩形状）。这正是"意图"的体现：目标是"进 band"，不是"挪 sd"。

### 4.4 R2 邻域加密：sd 步长自适应 + 允许 of 微调

- sd 步长从固定 ±2 → 按 `|target − seed.wr|` 用 1/2/3（与 `ApplyMandatoryTrackNudge` 一致，20pp→3、10pp→2、<10pp→1）。
- 微扰维度加入 `of`（当前只动 sd/ratios）：`of` 在 `[of±0.05]` 内微调，仅当该 band 会溢出（sd 高）时才有意义，低 sd band 跳过 of 微调。

### 4.5 预算与"倾向难带"

- R1a 按 band 播种后，剩余预算主要留给 R1b/R2，且**给"尚未满足且曲线陡"的 band 更高配额**（`CollectUnsatisfiedConfiguredTargetWinRates` 已知道哪些不满足，R1b 的 `CountSamplesInBand==0` 判断天然优先补没中的 band）。意图框架免费获得"难采段多给样本"。

---

## 5. 明确"不做"（不过度设计）

- **不铺开 sc**：sc 是粒度旋钮，本方案保持 `phase1FixedShuffleSplitCount`，避免把 4 维全打开。
- **不对 ratios 做全 5 段叉乘**：只用上面 6 个可名状原语 × 按 band 解出的 sd，绝不枚举 5^5 种 ratios。
- **不引入贝叶斯/GP 代理模型**：R1a 按意图播种 + R1b/R2 修正已能保证每个 band 有贴近候选，不值得在这个环节上复杂模型。
- **保留现有骨架**：R1a→R1b→R2 的流程、`phase1Samples` 软上限、`phase1WinRateMargin` 判定全都不动，只改"候选怎么生成"。

---

## 6. 落地改动清单（最小 diff）

集中在 `BlastMultiTierPhase1AdaptiveSampler.cs`，`BlastMultiTierOptimizer.cs` 只改调用处两三个字段：

1. `CreateFixedCandidate`：签名加 `float overflowFactor` 参数（或复用候选里的 of），不再恒用 `phase1FixedOverflowFactor`。
2. 新增 `IntentArchetype` 表（6 原语，见 4.1）。
3. `BuildRound1Plans` 重写为"按 distinct 目标 band 播种"：`BuildRound1IntentPlans(config, baseline, targets, seenKeys)`，内部做 band→sd 校准 + 原语变体。
4. `Round1BinaryFillMaxDepthPerSegment` 2→4；`ResolveBinaryMidStartDifficulty` 撞钳制时回退到切 ratios/of 变体。
5. `BuildRound2NeighborhoodPlans`：sd 步长自适应 + 微扰维度加 of。

> 全部改动 ≤ ~150 行，不动流程骨架，不扩预算，直击"85/65/50 缺档"的根因（sd 轴没按 band 铺开 + 二分深度不足）。

---

## 7. 对用户两例的最终裁定

| 用户提议 | 裁定 | 落地 |
|---|---|---|
| 洗牌少 → `sd=0, of=0` | ✅ 方向正确，采纳。注意 sd=0 是主导杠杆、of=0 在该端点冗余；**ratios 全 0 才是"不洗"的最强硬保证**（服务端 sum==0 直接零洗牌） | 编码为 `EASY_PLAIN` 原语：`(sd=0, ratios 全 0, of=0)` |
| `1,1,1,1,10 → 0,0,0,0,10` | ✅ 完全合理且更干净。`0`=该段退出洗牌池（比例分配 0 + 余数剔除 `RemoveAll`），`1`=以权重 1 参与。前四段从"被扰动 7%"变成"100% 保序" | 把 ratios 的 `0` 立为真实语义轴，preset 重写为 `0,0,0,0,10` 类 |

---

## 8. 关于"sd 方向"的源码纠正（重要）

任务描述称"sd 越低越难（洗牌重）"。源码实为**反的**：`sd → difficultyLoopOffset → difficultyIndex`，`sd` 越高 → 洗牌越多 → 越难 → 胜率越低。优化器内部 `ApplyMandatoryTrackNudge`/R2 也用"要更高胜率就 `-sd`"，与此一致。设计本身只用单调性，方向不影响方案结构，但**落地时要用源码方向**（85% 高难段的 sd 应比 baseline 更高，而非更低）。