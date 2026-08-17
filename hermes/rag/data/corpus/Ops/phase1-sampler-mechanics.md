# 多档位优化器 phase1 采样机制（C# 源码口径，2026-08-07 验证）

> 这是 Unity C# 优化器的 phase1 采样器机制速查，区别于 `design_probes.py`（探针工具链，见 probe-efficiency-standards）。改 phase1 采样前先读本文件，避免靠记忆猜参数链路。

## 核心文件
- `Assets/GameModule/Editor/Bot/BlastMultiTierPhase1AdaptiveSampler.cs`（532 行）：R1a preset / R1b 二分补洞 / R2 邻域加密 / EnsureUniqueCandidate / CreateFixedCandidate
- `Assets/GameModule/Editor/Bot/BlastMultiTierOptimizer.cs`（4168 行）：phase1 流程编排 + 预算分配 + 难度映射
- `Assets/GameModule/GameMain/Script/Sim/BlastDifficultyApplier.cs`：服务端洗牌分配（AllocateShuffleCounts / NormalizeRatios / ComputeDifficultyIndex）

## 机械参数链路（源码确认）
- **sd → 难度指数**：`difficultyIndex = difficultyLevel × levelDifficultyFactor + RoundToInt(startDifficulty)` → `numToShuffle = ceil(index/100 × size)`。sd 越高洗牌越多 → 一般越难胜率越低（**不绝对**：洗牌可能帮玩家把坏块洗开）。
- **of(overflowFactor)**：只在 `overflowTotal > 0`（某槽 requested 洗牌次数 > 该槽容量）时经 `overflowConvertedShuffleTimes = round(overflowTotal × of)` 生效。低 sd 端 numToShuffle 小 → overflowTotal=0 → **of 空转无效**（无副作用，只是表意性协同）。
- **ratios**：`NormalizeRatios` 输出长度 = `shuffleSplitCount`（=5），**只取 ratios 前 5 槽生效**，第 6+ 槽不参与。`AllocateShuffleCounts` 只看**相对比例** `raw = total × ratio / sum`；`sum<=0` → 全 0（零洗牌）；余数再分配时 `RemoveAll(ratio<=0)` 剔除 0 槽。
- **ratios 语义**：`0` = 该槽退出洗牌池（比 `1` 更彻底，最强"不洗"保证）。全 0 preset → CSV 输出 `0,0,0,0,0` → sum=0 → 真零洗牌。
- **ratios 等价性陷阱**：AllocateShuffleCounts 只看相对比例 → 同"参与槽集合"的 preset（如 `{10,10,0,10,10}` ≡ `{5,5,0,5,5}`，四槽均分）在 sim 中**完全等价**。改 ratios 后必须静态去重，不能靠运行时 EnsureUniqueCandidate（key 含 ratios 数组，等价 preset 的 key 不同不会自动去重 → 白跑两个相同 sim）。

## ToKey 去重
`ToKey = startDifficulty|shuffleSplitCount|overflowFactor(0.000)|ratios(完整数组含第6槽,逗号)`。sd 不同 → key 天然不同，不误伤。注意 key 含第 6 槽但 sim 只看前 5 → 第 6 槽恒 1 对 key 去重无干扰。

## phase1 流程与预算（Optimizer.cs 约 L745-975）
1. baseline（1 sample）→ `phase1SampleIndex=1`
2. **R1a**：`round1Count = min(Round1PresetCount, sampleSoftCap - phase1SampleIndex)`（L787-789）
3. **R1b**：cap = `min(Round1BinaryFillGlobalCap=16, 剩余)`，while 循环分段二分补洞
4. **R2**：`round2MaxPlans = 剩余`，邻域加密（每合格种子 densifyPerSeed 次）
- 三者共享 `sampleSoftCap = phase1Samples`，顺序 R1a→R1b→R2。
- **预算陷阱**：R1a 若空吃预算（如 80 候选全跑），`phase1Samples=100` 时 R2 只剩 3，邻域加密失效。**R1a 应给 R1b 保下限**：`round1Count = min(maxTotal, max(0, 剩余 - Round1BinaryFillGlobalCap))`。
- `CreateFixedCandidate` 被 LHS 采样等复用，split/overflow 统一走 `config.phase1FixedShuffleSplitCount` / `phase1FixedOverflowFactor`（默认 5 / 0.5）。若让 R1a 的 of 随 sd 变化，**不能改函数签名**，应在 BuildRound1Plans 内创建后 `raw.overflowFactor = ...` 覆盖。

## 已验证的 phase1 采样重设计方案（2026-08-07，结论：整体可行）
- **sd 五刻度** {0,10,20,30,40} × 16 ratios 全跑 = 80 候选，架构可行但需预算保底（见上）。
- **ratios 1→0**：语义正确，但产生 1 对冗余（#12 ≡ #15），需静态去重到 15 个有效模式（5单槽 + 4双槽 + 4三槽 + 1四槽 + 1全0）。
- **of 随 sd** {0,0.25,0.5,0.75,1.0}：单调协同方向正确；低 sd 端 of 空转但无害。
- **预算弹性**：裁剪 ratios 保 sd 端点 0/40（最难/最易）；外层 sd 顺序 `[0,40,10,30,20]` 截断即自然保端点。
- 不破坏 R1a→R1b→R2 骨架、phase1Samples 软上限、phase1WinRateMargin 判定。

## 排查口诀
- 高难段(85%)/低难段(50%) phase1 采不到 → 先查 R1a preset 是否全锁同一 sd（历史 bug：16 preset 全 sd=20、of=0.5 只在一维点附近探索）。
- 预算被 R1a 吃光导致 R2 无效 → 查 round1Count 是否有 `- Round1BinaryFillGlobalCap` 保底。
- ratios 改值后怀疑重复 → 用 AllocateShuffleCounts 相对比例口径手算参与槽集合，静态去重。