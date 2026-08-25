# BlastGame phase1 候选生成：intent-first（意图优先）而非参数网格

> 来源：2026-08 审查多档位优化器 phase1 采样设计的结论。源码实读为准。
> 产出完整方案备份：`<HERMES_ROOT>\phase1_intent_first_redesign.md`

## 机制校准（源码为准，四维参数的"玩法效果"）

- **sd（startDifficulty）＝难度主轴，单调。** `difficultyLoopOffset = startDifficulty`（BlastDifficultyContextFactory.cs:221,234）；`ComputeDifficultyIndex = difficultyLevel×factor + offset`（BlastDynamicDifficultyPureLogic.cs:75-77）；`numToShuffle = ceil(index/100×size)`（BlastDifficultyApplier.cs:126）。
  - **⚠️ 方向纠正：sd 越高 → 洗牌越多 → 越难 → 胜率越低。** 常见误说"sd 越低越难"是反的（优化器 `ApplyMandatoryTrackNudge`/R2 也用"要更高胜率就 `-sd`"）。设计只用单调性，落地用源码方向。
- **sc（shuffleSplitCount）＝把队列按进度切成 N 段**（`SplitGroupsByTargetProgress`）。是粒度/分布旋钮，不是难度主轴。
- **ratios（各段洗牌权重）＝洗牌在段间的分配**（`AllocateShuffleCounts(total, ratios)`）。
  - **`sum==0`（全 0）→ 直接返回全 0，一段不洗**（BlastDifficultyApplier.cs:299-300）。
  - 权重 0 的段在余数再分配时被 `RemoveAll(x=>x.ratio<=0)` 剔除（:333）。
  - → **ratios 的 `0` 是"该段彻底退出洗牌池"，比 `1` 更彻底**。这是真实语义轴，不是凑数。
- **of（shuffleOverflowFactor）＝二阶"溢出重排"旋钮。** 每段洗牌次数被 `cap=该段组数` 限制，装不下的算 overflowTotal；`of` 只出现在 `overflowConvertedShuffleTimes = overflowTotal × of`（BlastDifficultyApplier.cs:156-163）。
  - → **of 只在"洗牌溢出"（sd 高、洗得多）时才有作用**；低 sd（溢出 0）时 of 完全无效。网格里低 sd 放 of 是无效列。

一句话：**sd=难度档位主轴，ratios=洗牌空间形状，sc=粒度，of=仅高洗牌时生效的微调。**

## 用户偏好（一等信号）：intent-first，不要 parameter-grid

用户明确纠正主 agent 的"ratios×sd×of 三轴网格化"方案：**不要参数网格化，要从"玩法效果/胜率意图"去设计**。参数组合 = 一个玩法意图的编码，不是独立填格子。

用户两个例子（均已源码验证合理）：
- 要洗牌少 → `sd=0, of=0`：sd=0 是主导杠杆（numToShuffle=0）；of=0 在该端点冗余（无溢出）。**ratios 全 0 才是"不洗"的最强硬保证**（服务端 sum==0 直接零洗牌，即使 sd 钳制挪不动）。
- `ratios 1,1,1,1,10 → 0,0,0,0,10`：`0`=该段退出洗牌池（比例分配 0 + 余数剔除），`1`=以权重 1 参与。从"前四段被扰动 7%"变"前四段 100% 保序"。应把 `0` 立为真实语义轴。

## 反对参数网格化的 5 条论据（复用于后续审查）

1. **组合爆炸破预算**：5sd×5ratios×3of=75 格直接顶爆 `phase1Samples=100` 软上限；越粗越盖不全、越细越破预算——死结。
2. **网格无视 wr/sd 有序性**：把每个格子当独立点，浪费样本重测同一段单调曲线。意图设计把 sd 当共享已校准难度轴，ratios/of 只在每 band 内做形状多样。
3. **网格无法倾向难采 band**：85% 高难段曲线陡、要更密样本；50% 段平缓好采。网格一视同仁。
4. **of 分层是拍脑袋**：of∈{0,0.5,1} 在低 sd 格完全无效（无溢出）。
5. **治标不治本**：铺开 sd 仍无"每候选属于哪个 band"的意图标注，phase2 选五档仍靠"碰"。

## 落地方案（intent-first，极简不过度设计）

- **6 个可名状形状原语**（不是随机格子）：EASY_PLAIN / EASY_TAIL / MID_PLAIN / MID_TAIL / HARD_PLAIN / HARD_TAIL，覆盖"洗牌少↔多"×"均匀↔尾段集中"。
- **R1a 按 distinct 目标 band 显式播种**：band→sd 用 baseline 线性校准解出（`sdSeed(t)=clamp(sd_b + round((wr_b−t)/slope))`，slope 默认 ~5pp/sd，或用 baseline+1 探针实测标定），每 band 撒 2-3 个原语变体。~10-15 候选替换现 16 个锁 sd=20 的 preset，**保证 85% 高难段不再缺席**。
- **R1b 二分深度 2→4**；撞 sd 钳制时回退切 ratios/of 变体（sd 饱和后只剩形状杠杆）。
- **R2 sd 步长自适应**（20pp→3/10pp→2/<10pp→1，与 `ApplyMandatoryTrackNudge` 一致）+ 微扰维度加 of（仅高难溢出 band 有效）。
- **明确不做（不过度设计）**：不铺开 sc（保持 `phase1FixedShuffleSplitCount`）；不对 ratios 全叉乘；不引入贝叶斯/GP 代理；保留 R1a→R1b→R2 骨架与 `phase1Samples` 软上限。

## 落地改动最小 diff（集中在 sampler，~150 行）

1. `BlastMultiTierPhase1AdaptiveSampler.cs` `CreateFixedCandidate`：签名加 `float overflowFactor`，不再恒用 `phase1FixedOverflowFactor`。
2. 新增 IntentArchetype 表（6 原语）。
3. `BuildRound1Plans` 重写为按 band 播种（`BuildRound1IntentPlans(config, baseline, targets, seenKeys)`）。
4. `Round1BinaryFillMaxDepthPerSegment` 2→4；`ResolveBinaryMidStartDifficulty` 撞钳制切 ratios/of。
5. `BuildRound2NeighborhoodPlans`：sd 步长自适应 + of 微扰。