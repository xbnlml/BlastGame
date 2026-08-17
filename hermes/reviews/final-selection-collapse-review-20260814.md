# 防档位塌缩三方案评审：降序贪心 / DP联合 / 目标修正器档间修正（2026-08-14）

> 角色：算法复杂度/可维护性评审员
> 评审对象：`BlastMultiTierOptimizer.cs` `BuildFinalResultsFromCommonPool`（L1551-1684，逐档独立选档）+
> `BlastMultiTierTargetAdjuster.BuildAdjustedTargets`（91 行，Phase1 后/扩展后调用，L981/L1062）
> 数据：`_collapse_sim.py` / `_dp_gap_sim.py`（本评审新增）对 151-200 真实 verified 池子的三方案实测
> 需求：找档位时注意档位差；无硬性档差阈值；不降性能；方案别过于复杂。

## 一、评审结论（一句话）

**选 B（FinalSelection 内 gap-aware DP 联合选档）单独落地即可；A（降序贪心）在真实数据上被实测证伪（与现状零差异、0/3 塌缩被修），C（目标修正器软压）解决的是「目标可达性」而非「选档塌缩」，且其软压阈值与 B 的 gap 软分功能重复——B 单独就是「最简且能拉开档位差」的解。**

## 二、三方案对比表

| 维度 | A 降序贪心+单调上界+soft-overflow | B DP 联合优化 | C 目标修正器档间软压 |
|---|---|---|---|
| 改动位置 | FinalSelection 主循环（L1569-1644 重写） | 同左（主循环替换为 DP） | **另一文件** `BlastMultiTierTargetAdjuster`（Phase1 后/扩展后，L981/L1062） |
| 改动量 | ~100 行（主循环重写 + `tierMonotoneRelaxed` 字段 + CSV 列 + soft-overflow 降级链） | ~120 行（3 个纯函数 helper 对齐 find_best_combo + DP/回溯块，第二段展开循环不动） | ~40 行（单调修正 + 最小间隔软压 + 阈值常量） |
| 算法复杂度 | O(D·P log P) | O(D·P²)≈3k 次浮点比较，<0.1ms | O(D)，可忽略 |
| 性能/预算 | 纯逻辑，零新增 bot 局 | 同左 | 纯逻辑，但**改变 Phase2/3 候选窗口** → 重定向 bot 局数（预算不变、落点变） |
| 跨档信息 | 单调上界（顺序约束） | 单调(硬) + 档差软分进目标函数 | 只动目标，选档仍逐档独立 |
| 修倒挂 | ✅ 构造保证 | ✅ 构造保证 | ⚠️ 靠目标拉开间接缓解 |
| **修塌缩(gap)** | ❌ **实测 0/3** | ✅ **实测 3/3 全修** | ⚠️ 目标间距问题能修；选档问题不能 |
| 全局最优 | ❌ 局部（且顺序敏感、可能级联饿死） | ✅ | ❌ |
| 可维护性 | 中：soft-overflow/warning 分支多，目标函数仍无 gap 项，**"能跑但不解决问题"的隐患** | 高：教科书 DP；helper 与团队已信任的 `find_best_combo.py` 语义一致（消除工具链漂移） | 低：魔法常量（10pp 阈值/压幅）需调参；**静默改动设计目标**（targets 是设计契约）；与现有 clamp 逻辑叠加、交互难审 |
| 风险/副作用 | soft-overflow 增加状态面；tierMonotoneRelaxed 需维护 | 无（最坏退化为纯贴档） | 影响面最广：Phase2/3/FinalSelection 全部窗口随之偏移，需回归验证候选生成 |

## 三、实测证据（151-200 真实 verified 池子，`_dp_gap_sim.py` 可复现）

1. **A 与现状逐档独立选档在 50/50 关卡输出完全相同**（`_collapse_sim.py` 亦同）：真实池子里独立选档已经单调（无倒挂可修），单调上界不咬合任何一关——**A 的核心机制在真实数据上不产生任何效果**。
2. **塌缩案例 A 修不了、B 全修**（以 min 相邻有效档差计）：
   - L173 hard：A 2.3pp（33.3/31.0）→ B 9.3pp（T3→49.0，池子里有料，A 因"最贴目标 40"选了 33.3 而错过 49.0）
   - L194 hard：A 0.5pp（34.4/33.9）→ B 8.7pp（T3→49.5）
   - L197 hard：A 2.1pp（30.3/28.2）→ B 7.7pp（T4→37.9/T5→28.2，池子低端只有 28.2/4.2，属物理空洞，B 只能改善不能根治——这类该探针）
3. **B 在 45 个可解关中 22 关拉开 min 相邻档差、0 关变差**（L153 11.8→14.1、L158 9.0→19.5、L175 6.7→17.7、L177 10.2→21.0、L182 9.8→19.5…）。B 的所有输出仍在 ±10pp 硬门内、单调、配置互异（下标严格递增天然保证）。
4. 5 关为双失败（池子候选数不足）→ 属探针/改关卡问题，任何方案都不该背锅，保持现有失败路径即可。

**机制解释**：塌缩的根因（两份评审唯一的共识）是"目标函数里没有 gap 项"——逐档独立/贪心都是"最贴自己目标"，当 50% 段无候选时，中段档被迫选上探值，与相邻档贴到 0.5pp。A 只加"顺序约束"不加入目标函数，所以任何数据下都复现这个缺陷；B 把 `gap_score` 放进了目标，数据有余地时自动选拉开组合。

## 四、逐问回答

**1. 哪个最符合『简单』『能拉开档位差』？**
B。它只改 FinalSelection 一个函数的主循环（不动 Phase1-3、不动 bot 预算），gap 是软分不是硬阈值（符合用户否决硬门）、性能微秒级；且 B 的 helper（`TargetPenSeg`/`GapScore`/`ComputeTierGapRequirement`）直接照抄团队已在用的 `tools/find_best_combo.py`，语义零学习成本。A 同样简单但**实测拉不开档位差**（0/3），简单但无效不满足要求。

**2. C 单独用够不够？**
不够。塌缩的主体（L173/L194 这类）是**选档问题不是目标问题**：设计目标本身间距合理（10pp），池子里也有更拉开的好候选，是 FinalSelection"最贴目标"没选对。C 在 Phase1 后改目标，只会挪 FinalSelection 的 ±10pp 窗口，但 L173 的候选 49.0 在窗口 [30,50] 内、31.0 也在，目标 40→37 并不改变"最贴目标"选中 33.3 的结果——除非软压幅度大到把窗口整体移开，那就变成暴力调参且偏离设计意图。C 的定位应是另一类问题（目标可达性/教学期 95% 上限/物理不可达下压），不是档位塌缩的解。

**3. 要不要 C+（A 或 B）组合？**
不需要。C 的"最小间隔软压"与 B 的 `gap_score` 软分**功能重复**（都是"拉开相邻档"），只是位置不同（目标层 vs 选档层）；两层叠加 = 两个可调启发式互相干扰（C 改了目标 → 改 Phase2/3 池 → B 再在池上优化），正是用户否决的"复杂"。A+B 组合更没必要：A 的单调上界 = B 的硬约束、A 的 consumed = B 的下标严格递增，**B 是 A 的超集**。

**4. 有没有更简单的等价做法？**
B 本身已是最简形式。两个可选的"更简"方向（都不需要）：
- 枚举代替 DP：P≈25、D≤5 时单调剪枝后枚举实际极小，写法更直白（照抄 find_best_monotonic），但与 DP 实现量相当且无多项式上界——DP 已足够简单，不必换。
- 反向 gap-aware 贪心（自低档向上，候选按 贴档分+gap 分排序）：也能修一部分，但同样要引入 gap_score 管线、且无全局最优保证、还有"低档锚定抬高地板"的镜像风险——省下的复杂度不值得，不如 B。

## 五、最终推荐（怎么改最简）

**落地 B：只动 `BuildFinalResultsFromCommonPool` 主循环（L1569-1644），第二段展开循环（L1646-1684）与失败路径原样保留。**

具体最小改动：
1. 新增 3 个纯函数 helper（照抄 find_best_combo 语义，消除工具链漂移）：`TargetPenSeg(d)`、`GapScore(wrHi,wrLo,okLo,nearLo)`、`ComputeTierGapRequirement(tHi,tLo,out okLo,out nearLo)`（okLo=目标间距，nearLo=0.7×okLo，间距<5 时兜底 5/3.5）。
2. 主循环改为：distinct objectives 按目标降序 → 每档保留现有 `FinalHardGate`+`CloneEvaluationForTarget`+`UpdateCompositeScore` 过滤出 passed 列表（现状代码不动）→ 对 passed 按 PosteriorMean 降序排成 S → 跑 O(D·P²) DP（下标严格递增 ⇒ 单调+配置互异双保证；转移点同时算 target_pen + gap_score）→ 回溯得 rank0 组合。
3. gap 只软不硬：`gap_score` 只进目标函数，永不硬拒（"不设硬性档差阈值"的落地）；FinalHardGate 从"过滤器"降级为"超门标记器"（复用现有 `outOfTargetMargin`，不新增字段）。
4. 逐档失败/降级：候选不足时**不动现状失败路径**（failureByObjective / HasFailedTiers / best-available 展示）；需要区分"物理不可达 vs 候选缺口"时用现有 reason 机制，不新增状态字段。
5. rank>0 后备保持逐档 next-best（现状语义），不做联合保证。

**明确不做**：A 的 soft-overflow/`tierMonotoneRelaxed` 状态机（B 的 DP 天然降级，无需这套）；C 的档间软压（B 已覆盖 gap；C 的魔法常量调参会引入与设计意图的隐性漂移）。

**可选追加（1 行级，非本任务必需）**：若担心 adjuster 逐档 clamp 后目标倒挂的极端情况，可在 `BuildAdjustedTargets` 返回前加"单调修正：adjusted[i] = min(adjusted[i], adjusted[i-1])"——这是防御性一行，不是塌缩的修复。

**验证**：回归 4 个历史倒挂关 + 用 `_dp_gap_sim.py` 对 151-200 复跑，确认 22 关 min 档差拉开、3 个塌缩关 ≥7.7pp、0 新增失败。
