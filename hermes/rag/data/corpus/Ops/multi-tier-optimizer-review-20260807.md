# 多档位优化器（BlastMultiTierOptimizer.cs）设计审查 2026-08-07

> 独立审查（deleg_32110f03，逐行核对，未改文件）。源码 `<BLASTGAME_REPO>\Assets\GameModule\Editor\Bot\BlastMultiTierOptimizer.cs`（4168 行）+ `BlastMultiTierPhase1AdaptiveSampler.cs`。

## 流程（已确认）
```
phase0(现配400局) → 全部档位先验满足→跳过P1-3统一筛选
phase1(100局×N采样: base+Round1固定sd=20预设+R1b二分补洞+R2邻域加密)
phase2(追加100局→200局, top候选) → CredibleIntervalOverlapGate(SoftGap 8pp, absCap 12pp)
phase3(追加200局→320局, top3) → FinalHardGate(gap≤10pp, posteriorStd≤阈值)
final pool = phase0 + phase3 → BuildFinalResultsFromCommonPool(compositeScore排序选档)
```

## 关键设计事实（为什么这么设计）
- **phase2 不直接进 final pool 是合理的**：200 局是"探针级"样本，不是 verified。final pool 只收 phase0(400局 verified) + phase3(320局合并)。这正对齐"覆盖只认 verified"铁则。
- **phase3 合并重估是统计正确**：`MergeEvaluations`(L3411) 把 ph1+ph2+ph3 的 wins/losses 池化。seed offset 分段（ph1=0, ph2=ph1Runs*17, ph3=(ph1+ph2)Runs*17），是全新 bot 对局，非重跑。320 局合并估计比任何子集更接近真值。
- **贝叶斯自适应停止**：phase2/3 用 `posteriorStd < threshold` 达成即早停（可能不足 200/320 局），有后验保障，不是固定局数。

## L136 案例（66.5%@200 → 73.13%@320）
- 200 局 66.5% 的 95% CI ≈ ±6.5pp，真实胜率大概率落 [60,73]；追加到 320 局收敛到 73.13%（CI ±5pp），**73.13% 才是更可信的真值**。
- 66.5%@200 只是"碰巧贴目标"的小样本噪声点。合并重估没错，错在 phase1 没造出真正贴近 65% 段的候选 + final 选档无 gap 保障。
- 73.13% 满足 FinalHardGap(±10pp) 所以合法入库——用户看到"summary 选了 8pp 偏差"是事实，但根因在上游。

## 真实缺陷（对照铁则#4：五档单调递减 + 档间 gap≥15pp）
### 🔴 P0 最严重：final 选档完全没有跨档单调 + gap 校验
`BuildFinalResultsFromCommonPool`(L1532-1666) **逐档独立选**，只做 FinalHardGate(±10pp) + compositeScore 排序 + config-key 去重。**全文件 grep monotonic/单调/相邻/adjacent 无结果**。后果：5 档各自独立选，可选出 T3=73%、T4=52% 这种不单调、gap 不达标的组合，直接违反铁则#4。
→ 修复：选档后加跨档单调+T1≥T2≥…≥T5 校验 + 相邻 gap≥15pp(可放宽10pp标黄)；不符时在当档 pool 降级选次优直到满足或 HasFailedTiers。改动局限选档层，不碰探针管线，不加 bot 局数。

### 🟠 P1 根因：phase1 目标段采样密度不足
`BlastMultiTierPhase1AdaptiveSampler`：Round1 的 16 个 ratio 预设**全部锁死 startDifficulty=20**(Round1StartDifficulty=20)，只测 ratio 轮廓不在难度轴采样 WR 曲线；R1b 二分补洞每段最多 2 次(Round1BinaryFillMaxDepthPerSegment=2)；R2 只在已合格邻域加密。
→ 65% 段若 R1(全 sd=20) 测出的 WR 落在 50% 或 80% 侧，2 个二分中点可能直接从 50% 跳到 80%，永远落不进 [55,75] band → phase2 只能"就近"选真身 73% 的。
→ 修复：Round1 sd 覆盖 [startDifficultyMin, Max] 若干档位；二分深度 2→4 且以目标段 winRate 为锚在难度轴收窄。

### 🟡 P2 透明性：summary 不暴露重估漂移
summary 只显示合并值，不显示"200→320 局重估漂移 Δpp"→ 用户误判"被污染"。建议 ExportFinalCsv/summary 同时输出 ph1+ph2 探针值与合并后 verified 值并标 Δ。纯展示，零风险。

## 否决的方案（勿再提）
- **A. phase2 现货进 final pool** ❌：200 局是探针级非 verified，让噪声参与选档违反铁则#1。用户直觉"phase2 不该进"是对的。
- **B. phase3 独立验证不合并** ❌：120 局独立样本比 320 局合并更不可靠，正确性倒退。
- **phase3 后加"回退重跑"机制** ❌：用户反对过度设计；P1 修好根因后回退逻辑多余。

## 数据佐证：2026-08-07 批次 6 关（110_119-120_136_138_144）
- 110/136 跑完 phase0-3 有 summary；119/120/138/144 只到 phase1 停（phase1 后无合格候选晋级）。
- **6 关全部缺 T1/T2 的 85 段高胜率配置**（110/136 最高 0.82/0.84 差 3-10pp；119/120/138/144 直接 0 条）。
- 138 整体只 0.29~0.45，连 65 段都没有——关卡过难。
- 印证 P1：phase1 固定 sd=20 采不出真正的高难度(85)段。

## 用户核心设计原则（2026-08-07 纠正，最重要）：从玩法意图设计 phase1，非参数网格化
主 agent 曾提\"ratios × sd × of 三轴网格化铺开\"方案 → 用户否决：**不要参数网格化，要从\"玩法效果/胜率意图\"去设计 phase1**。
- **参数组合 = 一个玩法意图的编码**，不是独立填格子。每个候选回答\"我要打出怎样一个胜率/难度意图\"，而非\"我在网格里填一个 sd/of\"。
- 例：**要洗牌少 → sd=0 且 of=0**（两参数协同表达\"几乎不洗\"），不是分别调 sd 和 of。
- ratios `1,1,1,1,10` vs `0,0,0,0,10`：=0 的槽位分配 0 次洗牌（`AllocateShuffleCounts` 用 `Math.Max(0,ratios[i])`，0 槽 raw=0），`0,0,0,0,10` = 前4段完全不洗、只最后段重块，比 `1,1,1,1,10` 更彻底地表达\"只在最后重块\"意图。
- **不同难度档位已自带基础洗牌率差别，没必要再分**：`numToShuffle = ceil(difficultyLevel×levelDifficultyFactor/100×size)`（BlastDifficultyApplier.cs L126-128）。难度档(normal/hard/superhard)已决定基础洗牌强度，phase1 的 sd 是叠加其上的微调，不当作独立网格轴。
- 核心诉求：**phase1 尽量把 ratios/sd/of 三维都铺开覆盖**，但以胜率意图为目标生成候选，覆盖所有目标胜率段（85/65/50 等），不是机械填参数网格。

## ⚠️ sd 方向修正（2026-08-07 用户+审查双重确认，曾被主 agent 反说两次）
**sd 高 = 洗牌多 = 更难 = 胜率更低**，不是\"sd 低=难\"。源码：`difficultyLoopOffset=startDifficulty`(Factory:221,234) → `ComputeDifficultyIndex=difficultyLevel×levelDifficultyFactor+difficultyLoopOffset`(PureLogic:75-77) → `numToShuffle=ceil(index/100×size)`(Applier:126)。优化器内部要更高胜率就 `-sd`（ApplyMandatoryTrackNudge/R2 同向）。
- **85% 高胜率档 → 用低 sd**（简单）；**50% 低胜率档 → 用高 sd**（难）。
- **但 sd 高和 of 高都是\"倾向更难\"，不绝对**：洗牌有时把坏块/阻塞块洗开、洗到顺手位置，反而帮玩家 → 胜率未必单调降。of 只在\"洗牌溢出\"(洗很多)时才有效，低洗牌时 of 完全无关紧要(Applier:162-163)。
- 推论：**不能靠参数大小预判胜率档位，必须实测**（phase1 采样的意义）；**band→sd 线性解出只是\"种子\"不是\"保证\"**，要靠 R1b/R2 实测修正，不能假设 sd→胜率线性成立。

## 最终 ratios 方案（2026-08-07 用户拍板，替代 agent 的 6 意图原语）
用户倾向：**保留现有 16 个 ratio preset，把其中的 `1` 改成 `0`**（`1,1,1,1,10→0,0,0,0,10`、`10,1,1,1,1→10,0,0,0,0`、`10,10,10,1,1→10,10,10,0,0`、`10,1,1,1,10→10,0,0,0,10`），保留 16 种分布形状——比 agent 的 6 意图原语(EASY/MID/HARD×PLAIN/TAIL)更稳，因为覆盖更全且经实际验证，只加\"0 语义\"。
组合升级（三要素）：
- **ratios**：现有 16 preset 的 `1`→`0`（保留形状，加 0=退出洗牌池语义）
- **sd**：不再锁 20，按目标 band 用 baseline 线性解出（85→低 sd，50→高 sd，方向用源码）
- **of**：按 band 配（易→低 of，难→高 of），不再锁 0.5
- **sc**：保持 5 固定不变（用户确认\"sc5就够用了不用变\"）
- **修正**：sd/of 高=倾向更难但非绝对，band→sd 只是种子靠实测修正

## 工具经验
- **compare_level_db.py 匹配 DB 需归一化 ratios**：DB 存数组 `[10,1,1,1,10]`，asset/池子存字符串 `'10,1,1,1,10'`。旧 `str()` 数组→split 得 `['[10',' 1',...]` 永远不匹配→误报"无活动entry"。修复：norm_ratios 统一转 int 列表比较。扫 DB 问题关用它（活动 entry = fingerprint 匹配当前 asset 那条）。
- **探针中 = 待调优，不分两类**（用户 2026-08-07 纠正）：asset 已写探针的关和准备设计探针的关本质都是待调优状态，统一归"待调优"，不要再拆"探针中/待调优"。