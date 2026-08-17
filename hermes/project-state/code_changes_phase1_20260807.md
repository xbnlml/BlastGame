# 多档位优化器 Phase1 采样重设计 —— 代码改动记录

> 日期：2026-08-07
> 类型：Unity C# 源码改动（多档位优化器 phase1 候选生成）
> 状态：已改代码，静态检查+逻辑模拟验证通过（Unity 在跑数据，未做 batch 编译）
> 设计文档：`hermes/phase1_intent_first_redesign.md`（含审查 agent 校验报告）

## 背景 / 问题

phase1 负责"堆样本量覆盖目标胜率段"，让每个目标段（normal 85/85/65/50/50，superhard 50/40/30/20/10）都有贴近难度的候选。

**原实现缺陷**（已确认）：
- R1a 的 16 个 ratio preset 全部锁死 `sd=20`、`of=0.5`，只在一维点附近探索
- 难度轴完全没铺开 → 高难段(85%)/低难段(50%)采不到 → 6 关全缺 T1/T2 的 85 段

## 改动内容

### 文件 A：`Assets/GameModule/Editor/Bot/BlastMultiTierPhase1AdaptiveSampler.cs`

**1. 常量区**
- `RatioPresets`：原 16 个，全部 `1→0`（0=该段退出洗牌池，比 1 更彻底：分配 0 次 + 余数剔除）；**删冗余 #15 `{5,5,1,5,5}`**（≡#12，服务端只看相对比例）→ 有效 **15 个**
- `Round1PresetCount 16→15`
- `Round1StartDifficulty` 删除（不再锁 sd=20）
- 新增：
  - `Round1SdScale = {0,10,20,30,40}`（5 档难度轴刻度，含端点）
  - `Round1SdCount = 5`
  - `Round1SdOverflow = {0,0.25,0.5,0.75,1.0}`（随 sd 配 of）
  - `Round1TotalPresetCount = 5 × 15 = 75`

**2. `BuildRound1Plans` 重写**（R1a 候选生成）
- 从"16 循环锁 sd=20"改为"**外层 sd、内层 ratio** 双层循环"
- sd 遍历顺序 `[0,40,10,30,20]`（先保最易/最难端点）
- 每个候选 `raw.overflowFactor = Round1SdOverflow[sdIndex]`（随 sd 协同）
- `count` 参数兜底截断实现预算弹性

### 文件 B：`Assets/GameModule/Editor/Bot/BlastMultiTierOptimizer.cs`

**L787-789 `round1Count` 计算**
- 旧：`min(Round1PresetCount=16, 剩余预算)`
- 新：`min(Round1TotalPresetCount=75, 剩余预算 − Round1BinaryFillGlobalCap=16)` —— **给 R1b 永远保 16 下限**，避免 R2 被挤空

## 预算分配（验证通过）

| phase1Samples | R1a | R1b | R2 | 说明 |
|---|---|---|---|---|
| 20 | 3 | 16 | 0 | 预算少，R1a 只保端点 |
| 40 | 23 | 16 | 0 | |
| 100（默认） | **75** | 16 | 8 | 全铺 5sd×15ratio |
| 200 | 75 | 16 | 108 | R2 吃剩余 |

## 修订（2026-08-07 补充）：全 0 模板只配 sd=0

**改动**：
- 新增 `IsAllZeroRatios(int[] ratios)` 辅助方法（判断是否全 0）
- `BuildRound1Plans` 发射循环：全 0 模板只在 `sdIndex==0`（sd=0，最易端点）生成，其他 sd 跳过
- 候选数从 75 → **71**（省 4 次全 0 重复）

**验证**：括号配对 OK、IsAllZeroRatios 定义完整、逻辑模拟确认全 0 只出现 1 次配 sd=0、sd 覆盖 [0,10,20,30,40] 完整。

## 验证结果

- ✅ 括号配对：两文件全部 OK
- ✅ 逻辑模拟：80→75（去重后），sd 覆盖 [0,10,20,30,40] 全 5 档
- ✅ 预算弹性：R1b 永远保 16 下限
- ⚠️ 未做 Unity batch 编译（Unity.exe 正在运行，pid 30888，避免冲突）。待 Unity 空闲后 batch 编译验证。

## 明确不做（不过度设计）
- 不铺开 sc（保持 phase1FixedShuffleSplitCount=5）
- 不对 ratios 全叉乘
- 不引入贝叶斯/GP
- 保留 R1a→R1b→R2 流程骨架、phase1Samples 软上限、phase1WinRateMargin 判定
- R1b/R2 的 of 保持固定 0.5（未对齐 R1a，最小 diff 取舍）
## 修订 2（2026-08-07 补充）：R1b 二分深度 2→5 + 撞钳制转切 ratios/of

**问题**：R1b 二分补洞深度只有 2，sd 非单调 + 陡峭曲线（L51 实测差 1 档跳 53pp）下，2 个中点可能从 50% 直接跳到 80%，落不进目标 band。

**改动**（`BlastMultiTierPhase1AdaptiveSampler.cs`）：
1. `Round1BinaryFillMaxDepthPerSegment`: 2→5（相当于 10 刻度的细化粒度 40/2^5≈1.25）
2. `BuildRound1BinaryFillPlans`：当 `midSd` 撞到 `startDifficultyMin/Max`（sd 饱和）时，转切 ratios/of 变体：
   - ratios 对离目标更近的 bracket 做 ±1 扰动（探索新形状）
   - of 加变体（`overflowFactor + (depth%3)*0.1`）
   - targetLabel 标注 `(sd-clamped, ratios/of variant)`
3. 修正 `salt` 声明顺序（移到 `sdClamped` 判断之前，避免作用域错误）

**验证**：括号配对 OK、深度 5 确认、撞钳制转切逻辑确认、salt 作用域顺序正确。

**明确不做**：R1b 的 of 默认仍固定 0.5（未强制对齐 R1a 的 of 随 sd，仅在撞钳制时变体）——最小 diff 取舍。

## 修订 3（2026-08-07 补充）：R1a 分波次按需跑（Wave1/Wave2，借鉴旧机制 CountSamplesInBand）

**问题**：R1a 一次全跑 71 候选（5sd×15ratios），大量冗余（normal 关 sd=0 的 15 候选 wr 全挤 57-60%——difficultyLevel=0 时 sd0 不洗牌，ratios 无区分度），phase1 耗时 40+ 分钟（旧 32 候选 17 分钟）。

**方案**（agent 审查通过，deleg_e224ca0d 报告 r1a-wave-plan-review-20260807.md）：
- **Wave1（骨架）**：核心 5 单段 ratios × 5 sd = 25 候选（normal 关 sd0 只跑 1 个 → 21）
- **Wave2（按需补）**：对 (sd, target) 带内无样本的对补剩余 ratios（每对最多 10）
  - 覆盖判断复用 CountSamplesInBand（加 sd 过滤，按 (sd,target) 粒度）
  - normal 关跳过 sd0（不洗牌，不可达目标不白跑）
- 顺序：Wave1 → Wave2 → R1b → R2（R1b/R2/闸门/extension 零改动）

**改动**（sampler + optimizer 2 文件）：
1. sampler: `Round1CorePresetIndices` 常量（5 单段 {0,1,2,3,4}）
2. sampler: `BuildRound1Plans` 加 `presetIndices` 可选参数（null=全量向后兼容）
3. sampler: `CountSamplesInBand` 加 `startDifficulty` 可选 sd 过滤
4. sampler: 新增 `BuildRound1SupplementPlans`（Wave2，按 (sd,target) 覆盖补）
5. sampler: Wave2 normal 关（difficultyLevel==0）跳过 sd0；Wave1 normal 关 sd0 只跑 1 个单段
6. optimizer: R1a 拆 Wave1→Wave2（`ExecutePhase1Plans` 抽取评估循环复用）
7. optimizer: wave1Count 公式 = 5sd × 5核心

**效果**（逻辑模拟）：normal 关 61 候选（省 10），R2 预算 12→23；hard 关持平（不更差）。覆盖矩阵与全跑一致（Wave2 保证缺口段补齐）。

**验证**：括号配平 OK、逻辑模拟 OK（normal 21+40=61 / hard 25+50=75 worst case）。⚠️ 未做 Unity batch 编译（待 Unity 空闲）。

## 修订 4（2026-08-07 补充）：Final 失败保留 best-available（最优接近候选）

**问题**：final 选档失败（FinalHardGate 合格配置不足）时，`BuildFailedTierEvaluation` 返回空配置 + wr=0——用户看不到"实际能到多少"（L85 案例：T1/T2 目标 90%，phase2 有 81.2% 候选，phase3 追加后回归 <80% 没过门 → 显示 0，实际配置能到 80 附近）。

**改动**（`BlastMultiTierOptimizer.cs` BuildFinalResultsFromCommonPool）：
1. 遍历 pool 时跟踪 `bestAvailable`（离目标最近的候选，即使没过 FinalHardGate）
2. 失败分支（unique.Count < perTierCount）：bestAvailable 存进 `selectionByObjective` 作 fallback，标记 `status="failed"` + `failureReason`（不合格语义不变）
3. 展开处自动取用 → 失败档位显示最优接近候选的实际配置 + wr，而非空白 0

**验证**：括号配平 OK、逻辑确认（bestAvailable 声明/跟踪/fallback/failed 标记全 True）。⚠️ 未做 Unity batch 编译。
