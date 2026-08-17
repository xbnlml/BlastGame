# Phase1 ratios 模板设计要点（BlastGame 多档位优化器）

> 来源：审查 session（2026-08）。文件：`Assets/GameModule/Editor/Bot/BlastMultiTierPhase1AdaptiveSampler.cs`（RatioPresets L42-58 + 发射循环 L120-153）、`Assets/GameModule/GameMain/Script/Sim/BlastDifficultyApplier.cs`（AllocateShuffleCounts L288-370、BuildShufflePlan L116-166、SplitGroupsByTargetProgress L236-286、NormalizeRatios L202-234、ComputeDifficultyIndex L82-89）、`BlastMultiTierOptimizer.cs`（ToKey L171-188、ratio/startDifficulty 边界 L76-89）。

## 机制（按源码核实，评估模板前必读）

- **AllocateShuffleCounts(total, ratios)**：`raw = total × ratio / sum`，**只按比例分配，绝对权重值无意义**。
  - 单段 (10,0,..)/(5,0,..)/(1,0,..) 完全等价 → 都分配到满。
  - 全等权 (10×5)/(5×5) 完全等价 → 各段各分 1/5。
  - `sum<=0`（全0）→ 直接返回全0，**完全不洗牌**，与 N 无关。
  - 每段最终 `effective = min(分配值, 该段组数)`，溢出进 overflow（L150-157）。
- **numToShuffle 由 sd 决定**：`index/100×size`（L126），与 ratios 无关。**sd 是总强度轴，ratios 是位置分布轴，二者正交。**
- **关键推论（浪费根源）**：sd 越低 → N 越小 → rounding 把细粒度模板压平。例如渐变 (10,7,4,1,0) 在 N=5 时 round 成 ≈(2,2,1,0,0)，退化成≈前段；只有高 sd 才保留模板身份。**稀疏/渐变/全0 模板必须在高 sd 才有效，在低 sd 是噪音。**

## 审查结论

- **5 种单段 (位置=难度阶段 开局/前期/中期/后期/终局)**：全部保留，区分度最高、最直观，是 optimizer 定位"难度咬在哪"的核心词汇。
- **渐变模板 (10,7,4,1,0)/(0,1,4,7,10)**：基本无意义。低/中 sd 被 rounding 压平成≈子集模板；仅高 sd 有效但玩法与二进制子集模板重叠。若坚持要"渐进爬坡"最多留 1 个且只配高 sd。
- **全0 与 sd 配对方向**：全0@sd0 与一切@sd0 等价=浪费；全0@sd40 = "高强度但零洗牌" = 真正有信息量（分离数值难度 vs 洗牌难度）。**全0 应配高 sd。**
- **通用原则**：低 sd 只配核心代表模板；稀疏/全0/渐变模板往高 sd 放。

## 最终最优集（12 模板 / 60 候选，从 15×5=75 减到 60）

- 单段×5：(10,0,0,0,0)(0,10,0,0,0)(0,0,10,0,0)(0,0,0,10,0)(0,0,0,0,10)
- 子集×4：(10,10,0,0,0)前段 / (0,0,0,10,10)后段 / (0,10,10,10,0)中段 / (10,0,0,0,10)首尾 / (10,10,0,10,10)屏蔽中段
- 全段：(10,10,10,10,10)均匀
- 抑制：(0,0,0,0,0)全不洗 → **配高 sd=40**

（注：偶段 (0,10,0,10,0) 棋盘式可解释性差，建议换中段 (0,10,10,10,0)。）

## 反浪费 sd 配对（激进方案，需重构发射循环）

`sd0:1个` + `sd10/20:各6个(5单段+均匀)` + `sd30/40:各12个` = **38 候选**。彻底消除低 sd 的稀疏模板噪音。

## 工具链提示

- `read_file`/`search_files` 会把 UTF-8 C# 文件误判 binary，读源码用 `terminal grep/sed` 或 `terminal cat`。