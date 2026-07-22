---
name: blastgame-multi-tier-designer
description: "BlastGame multi-tier difficulty rules and reference. Level rules, data priority, checklists, tracing, probe design — used by level-optimizer and auto-pipeline."
version: 3.5.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [blastgame, game-design, difficulty-config, rules, reference]
    related_skills: [blastgame-level-optimizer, blastgame-auto-pipeline, blastgame-bot-orchestrator, blastgame-judgment]
---

# BlastGame 多档位难度配置 — 规则库

> **规则/知识库** — 不是流程。流程在 `blastgame-level-optimizer`，编排在 `blastgame-auto-pipeline`，Bot 批跑在 `blastgame-bot-orchestrator`。

## ⚠️ 目标胜率真源（铁律）

**目标胜率(T1-T5)的唯一真源是 `Assets/LvEditorConfig/lv_win_config_test.xlsx`。** 每关每档的目标值以 Excel 为准，不从 HANDBOOK、CLAUDE.md、memory、或本 skill 的内嵌表格读取。每次判定前必须读 Excel 获取当前目标值——Excel 中可能有策划手工修改过的特殊值，任何缓存/内嵌版本都可能过期。

**L51-100 特殊关卡：**

| 关卡 | 难度 | T1 | T2 | T3 | T4 | T5 | 说明 |
|------|------|----|----|----|----|----|------|
| L73 | normal | 100% | 100% | 100% | 100% | 100% | 蛇（新手关），全档100%，不适用常规判定 |
| L91 | normal | 90% | 90% | 75% | 60% | 60% | 锁（新手关），目标同普通Normal但判定放宽 |
| L98 | superhard | 60% | 45% | 30% | 20% | 10% | 特殊目标值 |
| L100 | normal | 90% | 90% | 70% | 50% | 50% | 特殊目标值 |

> 新手关可 100% 胜率，不适用常规判定标准。但 L91 的目标值仍是标准 normal（90/90/75/60/60），只是判定时放宽——不是全 100%。

## Level Rules

| 类型 | 有效档数 | T3锚点 | 档差要求 |
|------|---------|--------|---------|
| Normal | 3套(T1=T2,T4=T5) | ≥60% | T1→T3 ≥ 15%，T3→T5 ≥ 15%，最佳 20-35% |
| Hard | 5套各不同 | 30-60% | 各档差尽量 ≥ 10%，最佳 15-20%，底线 5% |
| SuperHard | 5套各不同 | ≤50% | 各档差尽量 ≥ 10%，最佳 15-20%，底线 5% |

**硬性违规：** 档差<5% / 档差>40%（仅Hard/SuperHard，Normal 3-tier不设上限）/ 倒挂超1% / T3锚点不符 / 任意档<5% / <10%档>1个。

**档差审美（推荐，非强制）：** >50% 段 15-35pp 可接受（最优 20-30pp），<50% 段 5-25pp 可接受（最优 10-20pp）。递减：高>中>低，低档差超高档差 ≤4pp 允许。

**倒挂处理：** T5 > T3 或 T4 > T3 等倒挂可以用不同 slot 的配置互换解决。Bot 验证时各档配置都是独立验证的，不代表只能固定用对应 slot。调整时只需确保 WR 降序 T1 > T3 > T5（或 T1 > T2 > T3 > T4 > T5），任意配置可分配到任意档位。

**sd/WR 非线性：** 四参数(sd/sc/ratios/of)与胜率不是线性关系。sd 降 2 点 WR 可能涨 30pp 也可能降 10pp。看实测胜率，不靠公式推。**sd 增加不保证 WR 降低，sc/of/ratios 同理。非单调是常态，不是数据错误。**

## 结论前强制检查

**① 数据源判定：** Bot / +Summary / +Phase2 / +Phase1 / +自推？够不够？

**② 合格判定：** 所有档≥5% / <10%档≤1个 / 相邻<40% / T3锚点 / 不倒挂 / Normal T1→T3≥15%且T3→T5≥15% / Hard各档差≥10%

**③ 数据展示规则：** 所有数据必须用表格呈现，一档一行，禁止纯文字叙述。表头含：档位/WR/sd/sc/ratios/of。对比数据时必须并列显示（实测 vs 目标）。

**④ 硬性违规清单（逐条核对）：** 档差<5% / 档差>40% / 倒挂超1% / T3锚点不符 / 任意档<5% / <10%档>1个

**判定前必须加载 judgment-rules.md 参考文件，过完 ①数据源 ②合格判定 ③数据展示 ④硬性违规 ⑤结果分级 再下结论。** 不得凭记忆判断规则。
加载命令：`skill_view(name="blastgame-judgment", file_path="references/judgment-rules.md")`

**⑤ 结果判定：**
- ✅ **合格** → 入库
- ⚠️ **接近**（各档WR离目标≤5pp，或档差缺≤5pp）→ 记录最佳方案到 tuning-records.md，标记"待确认"，不做改关卡标记
- ❌ **远不合格**（WR差≥10pp，或硬性违规）→ 继续下一轮 / 第6轮仍不合格→标记改关卡

**判定原则：**
- **先展示最佳方案，不自己判死刑** — 所有数据点穷举后，把最接近目标的组合展示给用户，让用户决定是否接受。规则是参考，不是铁律。
- **检查表不过≠直接改关卡** — 接近目标（差≤5pp）的方案标记"待确认"，可能用户会接受。
- **结果三分级：** ✅合格（入库） ⚠️接近（标记待确认） ❌远不合格（改关卡）

> **天花板限制：** 如果 sd=0 或最低可用 sd 仍然达不到目标 WR，说明该关卡存在固有胜率天花板（游戏随机性/机器人水平限制），不可能通过调 sd 达到目标。这种情况标记改关卡，不需要跑满 6 轮。

### 死亡分布辅助预判

有 failBucketDistribution 数据的关卡，R1 后多一条判断（仅用于需要高胜率的档位，如 T1/T2 目标≥60%）：

```
1. 读最佳组合 T1 的 earlyDeath（桶 0-1 和）
2. 算阈值 = (1 - 目标WR) × 80%
3. 如果 earlyDeath > 阈值 → 标记改关卡，不走 6 轮
4. 否则 → 继续正常调试
```

**原理：** 初始牌面死亡占比 > 阈值时，即使后段降到零难度也救不了那部分玩家。和 6 轮上限配合使用，不是替代。

## 合批验证

同难度类型的关可以合并到一个 request 提交，Bot 逐关读各自 asset。

**Normal（3 档配置 T1=T2,T4=T5）：** `"tiersCsv":"1,3,5"` 只跑 T1/T3/T5
**Hard/SuperHard（5 档配置）：** `"tiersCsv":"1,2,3,4,5"` 跑全部

**levelSpec 格式：** `"52,54,64,65,70"` 逗号分隔 或 `"52-55"` 范围

### 验证方法与结果判定

1. 按难度分组合批提交
2. 读结果时按关+按档对比：
   - campaign-summary 获取 WR
   - campaign-attempts 获取实际配置（sd/ratios）
3. **判定：**
   - 配置不一致 → asset 没同步，需更新
   - 配置一致但 WR 差>10pp → 关卡可能被改过，标记重新优化
   - 配置一致且 WR 差≤5pp → 验证通过

### 合批 monitor 注意事项

合批时 T1 完成后 export 文件 mtime 变更会触发 monitor 退出，此时 T2-T5 仍在跑。需要重启 monitor 等待后续结果。

**槽位分配规则：**

对 T1-T5 各档位分别看当前最佳配置离目标还有多远。缺口越大的档位分越多槽，缺口 5pp 以内视为已通过、不分槽。5 槽全部用在仍有缺口的档位上，不浪费在已验证的配置上。

## 快速预筛（省时策略）

从 L51-100 批量数据或任何已有数据可快速预判关卡是否值得调：

- **窄带 + 远低于目标：** 如果同一 sd 下所有档位 WR 接近（差≤5pp），且最佳 WR 离 T1 目标 ≥20pp → 该关卡有 WR 天花板 → 无需开跑，直接标记改关卡
- **窄带 + 接近目标：** 如果窄带但最佳 WR 离 T1 目标 < 10pp → 还有机会，跑第 1 轮探天花板
- **宽带：** WR 分散（差≥15pp）→ 调节空间大，值得跑多轮

## 多轮调优要点

- 已验证的 Bot 配置不放下一轮探针
- 每轮后从全部数据池重选最优 5 档（含本轮 + 过往全部数据）
- 胜率接近时（±3pp）优先选轮次更新、数据更多的
- 已验证条件：campaign-attempts 可查到该四元组且≥400局
- **明显不合格的方向不要直接放弃，用剩余轮次继续探。**
- **分析死亡分布：** 死亡集中在游戏前期→初始牌面问题，参数难解决。分散在全游戏→参数还有空间。
- **轮次仅消耗于有效运行：** 因 asset 未刷新、request 被跳过、配置不对等故障导致数据无效的轮次，**不消耗**轮次上限。每次 Bot 跑完后核对 attempts CSV 确认配置与探针一致，一致才计为有效轮次
- **查全部数据池组合再结论** — 做最终判定前，穷举所有历史数据点，检查是否有合格或接近的组合
- **Opt 仿真数据 ≠ Bot 实测数据：** Phase1/2 使用仿真引擎，WR 结果可能比真实 Bot 跑分高 5-15pp。不可直接用 opt 的 WR 替代 Bot 验收。仿真仅用于筛选候选，最终验证必须用 Bot 批跑

## 目标可调整性

目标 WR 是参考方向，不是铁律。如果天花板够不到目标：

- **T1 达不到目标：** 适当降 T1 目标，同步降 T3/T5 目标，维持最少 15pp 档差
- **T5 达不到目标：** 适当升 T5 目标，确保 T3→T5 ≥ 15pp
- 但 T3 锚点（Normal≥60%）是硬底线，不能突破
- 最终方案在 tuning-records.md 记录「实际采用的目标」

## Data Priority

Bot400 = Summary400 > Bot200+ = Summary200+ > Phase2 > Phase1 > 自推

> **优先级规则：** bot 高于 summary（同局数下 bot 优先），但 summary≥400 局可信不需重验。

> **⚠️ Phase 2 推荐配置的 WR 是模拟值，不是 Bot 实测值。** 模拟 WR 可能比 Bot 实测高 10-30pp。不能直接以 Phase 2 推荐做最终判定，必须先跑 Bot 验证。Phase 2 只用于"推荐配置方向"，不用于"确认配置合格"。

| 元数据 | 真源 |
|--------|------|
| 目标 WR (T1-T5) | `Assets/LvEditorConfig/lv_win_config_test.xlsx` |
| 难度/教学关 | `Doc/1-200关设定.xlsx` C/E 列 |
| 已入库配置 | `Doc/手动挑配置记录.xlsx`（非难度真源） |

## 探针设计原则（需求驱动）

**设计探针前加载 `references/probe-design.md`，按①需求驱动流程 + ②调参经验 + ③四个参数本质区别 + ④微调法 执行。**

永远从"需要什么胜率"出发，不是"跑多少轮"。

**决策流程：**
1. **需要哪些 WR？** 算档差需求，确定每档目标WR范围
2. **按数据源优先级检索已有数据：** Bot → Summary → Phase2 → Phase1 → 自推。高优先级有数据时不查低优先级
3. **缺哪些 WR 段？** 对比需求 vs 已有
4. **全段都缺？** → 宽谱（首次无数据时）
   **部分段缺？** → 精准填空，槽位全打缺口
   **不缺？** → 直接从已有数据组合
5. 已有覆盖的 WR 段不给槽，不必要的区域不给槽
6. **标来源（按 sd/ratio 逐源匹配，不是按 WR 段查）：** 对每槽的 sd/ratios 组合，按优先级顺序逐源检查：Bot → Summary → Phase2 → Phase1。前三者有该配置则标那里；都没有才标"自推"。"自推"代表该 sd/ratios 组合在所有数据源中均不存在，不是"这个 WR 段没人跑过"。

**调参范围与经验：** sd/sc/ratios/of 四参数全可调，不限于 sd，没有固定顺序。根据实际情况合理选择。

| 参数 | 效果 | 使用建议（经验参考，非硬性） |
|------|------|---------------------------|
| sd | 主难度控制 | 最直接。建议先用极端值（3-50）摸清 WR 范围 |
| sc | 精细度控制，不是难度控制 | **通常 sc=5 优先**，效果不佳再考虑调整。L51 卡 sd 时换 sc=3 突破，但 L55 sc=5 配合极端 sd 也够用 |
| ratios | 难度分布调节 | 跟 sd/sc 协同调整 |
| of | 强力辅助，非线性 | 建议先用边界（0 和 1）摸范围，再小步调（步长 0.05-0.1）。of=0→0.5 可能跳 60pp，不敢调不如不调。⚠️ of=0 可能导致部分关卡崩溃，改为 of=0.01 可避免 |

**如何选择调参方向：**
- 某个参数多轮无效，应该考虑切换方向，可能不同关卡对不同参数的敏感度不同
- 建议先极端值探边界，再在边界内精调

**实战案例：** `references/parameter-tuning-lessons.md` 有 L51（7轮）vs L55（4轮）的完整对比，展示了这些原则如何在实际中应用。



**详细参数经验（延续上表）：**

| 参数 | 效果方向 | 经验 |
|------|---------|------|
| sd 提高 | 难度提高，WR下降 | 非线性明显，不保证单调 |
| sd 降低 | 难度降低，WR上升 | |
| sc 提高 | 洗牌段数增多，难度提高 | |
| sc 降低 | 洗牌段数减少，难度降低 | sc 切换能突破 WR 天花板（L51 换 sc=3 解决了 sc=5 的断层问题），但 **sc=5 优先，非必要不改** |
| ratio 左移（高位牌号前移） | 底部牌更多，难度降低 | |
| of 提高 | 洗牌溢出增多，难度提高 | of 在 0.3-0.5 区间有陡峭响应曲线。0.5→0.3 可能跳 58pp。调 of 建议步长 0.02-0.05 |
| of 降低 | 洗牌溢出减少，难度降低 | 极端情况 of=0 可能接近 100% WR |

**设计探针时四参数应协同考虑，不要只调 sd。参数非线性经验详见 `references/parameter-nonlinearity-lessons.md`。**

**从评判标准反推需求：** 合格的档差要求（如档差递减）可以反推出需要的 WR。如果 T1→T3=22pp，档差递减要求 T3→T5 ≤ 22pp（允许超 4pp），则 T5 ≥ T3 - 26pp。

## 死亡分布分析

> ⚠️ 旧的 timeSec/P50 方法已被 failBucketDistribution 替代。新方法使用 campaign-summary CSV 自带的 10 桶死亡分布。

**数据来源：** campaign-summary.csv 的 `failBucketDistribution` 字段（10 个桶，等分游戏总时间）。
**工具链：** `find_best_combo.py` 自动读取并显示死亡分布 + 改关卡预判。

**10 个桶对应的游戏阶段见 `references/probe-design.md` §死亡分布。** 快速参考：

| 桶 | 阶段 | 调参能力 |
|----|------|---------|
| 0-1 | 初始牌面（0-20%） | ❌ 参数无效，改关卡 |
| 2 | 过渡段（20-30%） | ✅ ratios 前段/sd |
| 3-5 | 中期（30-60%） | ✅ of/ratios |
| 6-9 | 后期（60-100%） | ✅ of/后段 ratios |

**改关卡预判：** `earlyDeath(桶0-1) > (1 - 目标WR) × 80%` → 初始牌面死亡超标，改关卡（仅用于 T1/T2 高胜率档位）。

## 数据追溯

**用 sd/sc/ratios/of 四元组匹配，不用档位标签或胜率匹配。**

```python
def norm_ratios(r):
    if not r: return ""
    try: return ",".join(str(int(float(x))) for x in str(r).replace(" ","").split(",") if x.strip())
    except: return str(r).replace(" ","").strip()
```

`campaign-summary.csv` 无配置参数，`campaign-attempts.csv` 才有。

**Opt 数据多目录问题：** 同一关可能出现在多个 opt 目录（如单独跑 `51-51-*` 和批量跑 `51_58-62_64_68-70-*`）。
读数据时必须取最新目录，跳过旧跑结果。批量目录名格式：`{level1}_{level2-range}{level3}_{level4-range}-{timestamp}`

**手动挑配置记录.xlsx 读取要点：** 该文件每关 5 行（Tier1-Tier5），关卡号列使用合并单元格。
不能简单用 `ws.cell(row,1).value` 读所有行，必须通过 `ws.merged_cells.ranges` 构建行号→关卡号映射：

```python
row_lv = {}
for mc in ws.merged_cells.ranges:
    if mc.min_col == 1:
        top = ws.cell(mc.min_row, 1).value
        for r in range(mc.min_row, mc.max_row + 1):
            row_lv[r] = top
```

**程序化生成关卡与手作关卡的区别：**

| 类型 | asset 文件大小 | 有无 customCellDrawingListV2 | 特点 |
|------|-------------|---------------------------|------|
| 手作 | 1000-2000行 | 有 | 关卡设计师手动摆块，独立配置 |
| 程序化生成 | ~47行 | 无 | 运行时算法生成，只有 stack 基础参数 |

程序化关卡 asset 文件仅包含 DynamicDifficultyConfigs + 基础 stack 参数（width/height/StackHeight/TowerValue/PoolValue）。
这是正常结构不是损坏。仿真时关卡由算法实时构建。

## 知识分层标准（Memory vs Skill vs fact_store）

| 放哪里 | 内容 | 示例 |
|--------|------|------|
| Skill | 项目知识，换人做也得知道 | 数据真源、目录格式、检查表、脚本索引 |
| Memory | 跟这个用户配合的方式 | 中文、简洁、先给结论、不ask继续吗 |
| fact_store | 每关主观讨论 | 为什么选A不选B、用户倾向、非客观需求 |

Memory 每轮全量注入，只存少量工作方式。关卡细节存 fact_store 按需检索。

**Memory 与 Skill 去重原则：** skill 已有的规则/流程/技术细节不应再出现在 memory 中。memory 只保留用户偏好（沟通方式、工作习惯）和强制行为触发（判定前加载规则、加载 skill）。

## 典型错误

1. 不先过检查表就猜配置
2. 已Bot验证的配置放探针（已验证绝不重跑）
3. 跳过数据源直接判改关卡
4. 只搜单关目录模式，漏了范围模式
5. patch asset 后不等 Unity 重载就写 request，白跑一轮
6. 写 __ForceReload.cs 多余触发 domain reload
7. Agent 往前跳，做用户没要求的事
8. 胜率接近时不用旧数据只用本轮
9. 不用表格展示数据，用文字叙述
10. 从单一数据点推结论（如 sd=0 出 54% 就说"有自然上限"）→ ❌ 四参数非线性，展示数据让用户判断
11. 写死槽位分配数字（如"最多1槽""至少2槽"）→ ❌ 规则只给原则，不给定额
12. **用 `write_file` 修改 .asset** — .asset 是混合格式文件，覆盖即损坏。必须用 `patch` 只替换 `DynamicDifficultyConfigs:` 区块
13. **窄带直接判死刑** — 窄带但 WR 接近目标时仍有空间，先探天花板再决定
14. **不看死亡分布就下结论** — WR 低可能是参数问题也可能是牌面问题，先分析再判
15. **Excel 合并单元格不处理导致读不全** — 手动挑配置记录.xlsx 每关 5 行用合并单元格存关卡号，必须构建行→关卡映射
16. **数据源被删后不标记** — 如果 telemetry/bot 被清理，已 Bot 验证的记录在 手动挑配置记录.xlsx 里。不在记录里的需要重跑
17. **白跑轮次计入 4 轮上限** — asset 没刷新等故障不消耗轮次
18. **未经用户确认标"完成"** — 只有用户同意的才标完成。跳过的标"Agent完成"，接近的标"待确认"
19. **批量改 asset 时用 str.replace 替换重复值** — 5 个相同 sd 值用 `replace(10, 8, 1)` 会替换错位置。必须用行号索引替换
20. **忽视 of，只调 sd** — of 是四参数之一，降低 of 提高 WR，提高 of 降低 WR。sd 调不出时试试改 of
21. **regex 缩进 5 空格误删手配排面** — `customCellDrawingListV2` 在 asset 中是 4 空格缩进，5 空格正则会退到 `\Z`，删除整个文件尾巴（含手配排面）
22. **全自动模式还提问题等确认** — 用户说了全自动或我人不在了，不再展示方案、提问、等确认。走三批流程（决策→执行→裁定），不等确认。
23. **标来源时不按 sd/ratio 逐源查** — 标来源前未按优先级逐源匹配具体 sd/ratios 组合。标 Phase1 前必须确认 Phase2 无该组合，标自推前必须确认 Phase1 也无。不要按 WR 段反推标源
24. **白跑验证时机错误** — 白跑验证应在提交 request 前完成（确认 AssetDatabase 已刷新），而非 Bot 跑完后。跑完后查 attempts 仅用于判定是否计入轮次
25. **of 跳步太大** — of 在 0.3-0.5 区间响应陡峭，0.5→0.3 可能跳 58pp。建议步长 0.02-0.05
26. **探针方向判断错误** — 不是"哪个区域数据少就打哪"，而是"哪个标准没满足就解决哪"。T1→T3=18.5pp<20pp 的问题应该打 T3 方向，不是打 T5 方向。需求驱动的核心是反推标准缺口，不是填数据空白
27. **审美差≤2pp 仍判接近** — 档差审美是推荐非强制。当偏离推荐值≤2pp 且无硬性违规时，可直接判合格
28. **of=0 导致 simulation crash** — 部分关卡 of=0 会触发 BlastInitialQueueBuilder 队列构建异常。用 of=0.01 替代 of=0 可避免，效果近似
29. **PollForRequest 未启动时试图重启 Unity** — 聚焦 Unity → 等待编译 → 仍不管用则删除 request 并重新写入（delete+recreate 触发文件 watcher）。最后手段：touch BlastBotAutoBatchTrigger.cs 追加注释触发 domain reload。禁止随意重启 Unity，但**卡死/崩溃时重启 Unity 是故障修复，不受此限**
30. **Bot 崩溃不产出 export 文件** — `Assets/Editor/` 下的脚本无法引用 `GameModule.*` 命名空间的类型（如 `LevelProfileConfig`）。Editor 程序集与游戏程序集分离。想验证 asset 配置只能通过反射或读文件，不能用 `AssetDatabase.LoadAssetAtPath<LevelProfileConfig>()`
30. **Editor 脚本引用游戏程序集类型** — `Assets/Editor/` 下的脚本无法引用 `GameModule.*` 命名空间的类型（如 `LevelProfileConfig`）。Editor 程序集与游戏程序集分离。验证 asset 配置只能通过反射或读文件，不能用 `AssetDatabase.LoadAssetAtPath<LevelProfileConfig>()`\n31. **Bot 崩溃不产出 export 文件** — monitor 依赖 `auto-batch-last-export.txt` mtime 变化。如果 Bot 进程在 export 前崩溃，monitor 永远检测不到完成。跑完后检查：目录存在但没有 CSV 数据 → Bot 没跑成 → 检查 Editor log 找错误 → 重跑\n32. **全自动模式写自治脚本** — 绕过 agent 决策的脚本（如 auto_pipeline.py 旧版）跳过 skill 文件加载。必须按三批流程执行，决策步骤（批A/批C）加载对应 skill 文件。\n33. **focus Unity 超时** — WScript.Shell.AppActivate("BlastGame") 可卡死。用 subprocess.Popen + timeout 或用 start /B 后台启动，不 blocking 等待。\n34. **export 后检测不到完成** — submit_batch_unity.py 在 batch mode 完成后自动退出，刷池子。如超时，检查 `telemetry/bot/` 目录是否有 CSV 数据
35. **用内嵌/缓存的目标胜率表代替读 Excel 真源** — HANDBOOK、CLAUDE.md、本 skill 的 Level Rules 表中列出的目标值是通用模板，不是每关的真实目标。**每次判定/设计探针前必须读 `lv_win_config_test.xlsx` 获取当前目标值，不信任任何内嵌副本。**
36. **`find_best_combo` 难度检测失败导致 Normal 关跑成 5-tier** — `find_best_combo.py` 从 diff_map 取难度，若失败回退到 `hard`（5-tier O(n⁵)）。Normal 关走 5-tier 比 3-tier O(n³) 慢 600+ 倍。**必须用 `excel_target` adapter 读难度**，不依赖 asset 文件。已在 pool.py 优化（窗口剪枝+内层gap预剪），但正确检测难度是根本解。
37. **`find_best_combo` 打分偏重目标差、轻档差** — 旧版只罚 gap 太小，不罚 gap 太大/不在审美区间。优化后 `_gap_score`：硬违规×20，审美偏离×3~5。用户优先级：档差质量 > 目标接近度。详见 `tools/data/pool.py`。
38. **board.md 与 Excel 实际数据不一致** — board 标注"待选配"的关可能在 Excel 中没有配置（如 L96 有池子数据但 Excel 无 sd）。开工前读 Excel 交叉验证，用 `手动挑配置记录.xlsx` 中 sd≠None 判断哪些关有实际配置。
39. **Normal 3-tier 档差上限不要硬判违规** — Normal 只有 3 档有效（T1=T2, T4=T5），T1→T3 和 T3→T5 可自然达到 30-50pp，不设 >40% 硬违规。仅 Hard/SuperHard 有档差上限。
41. **ratios 逗号数 ≠ sc** — 探针配置中 `ratios` 切割后的数量必须等于 `sc`。sc=5 但 ratios 只写了 4 个值（如 `2,0,5,2`）→ Unity 抛 QueueParity 异常，Bot 崩溃。从池子取记录或手动构造探针时，**写入 asset 前验证 `len(ratios.split(',')) == sc`**。phase2 数据可能带非标准 sc（sc=4），保持原样即可，不需要改成 5。
42. **探针只朝一个方向调 of** — of 的方向在部分关卡是**反向**的。L59 of↓(0.5→0.03) 反而 WR↓(77%→50%)。同一关卡 of 方向也可能不同（有些正常有些反向）。**先用边界值双向探方向**（同时跑 of=0.01 和 of=1），确认方向后再梯度探测。
43. **参数死区不识别白白浪费轮次** — 多轮探针发现不同参数值产出相同 WR → 该参数在当前关卡有死区。如 L81 of=0.11~0.4 全部产出 86.5%，L86 of=0.15~0.8 T1/T3 纹丝不动。发现死区后立刻切换参数或接受跳崖值（of=0.107→55%），不要在同一参数内继续梯度探测。
44. **`find_best_monotonic` 参数传错位置** — `find_best_monotonic(records, targets, top_n=1, difficulty='hard')` 第3个参数是 `top_n`，不是 `difficulty`。常见错误：`find_best_monotonic(pref, targets['tiers'], targets['diff'])` 把 `'normal'/'superhard'` 当成 `top_n` 传进去，导致 `candidates[:'normal']` 抛出 `TypeError: slice indices must be integers`。必须用关键字参数：`find_best_monotonic(pref, targets['tiers'], difficulty=targets['diff'])`。
45. **WR 天花板 ≠ 参数死区，混淆导致误判** — 两种不同的调优瓶颈需要不同对策：\n    - **参数死区**（如 L82）：sd=1 和 sd=45 用相同 ratios 产出相同 WR（如 81.25%），sc=4/5/6 也无变化。参数完全无效 → 改关卡。\n    - **WR 天花板**（如 L98）：参数有效（sd 从 1→20，WR 从 3.5%→46.25%，范围 42pp），但即使最低难度也达不到目标值（T1 目标 60%，实测最高 46.25%）。检查方法：看数据 WR 范围是否足够宽（≥30pp）来判断参数是否有效。参数有效但达不到目标 → 仍然改关卡（天花板），但理由≠死区。\n    - **区分方法：** 对现有数据按 WR 排序，看 sd/ratios 变化时 WR 是否有实质性变化（≥10pp）。有变化→有参数响应→不是死区。但最高 WR 仍远离目标→天花板。\n46. **改名后文件引用漏查** — 重命名文件（如 Excel 改名）后，只更新了文档没更新 Python 工具中的硬编码路径。rename 后必须用 `rg "旧名字" D:/path/ --glob '!_archive/**'` 搜索所有非归档源文件，逐处更新。\n47. **`search_files` 路径格式问题** — 该工具底层用 Windows 原生 rg，不支持 MSYS2 `/d/` 路径。必须用 `D:/` 格式传 path 参数。\n48. **SuperHard 底板锁死，参数无法补偿** — SuperHard (difficultyLevel=2) 的基础难度远大于 sd/ratios/of 的调节范围。L98 实测：sd=0 + r=1,1,1,1,1 + of=1.0（全部拉到最易）→ 全档仅 1% WR。发现此信号后立即标记改关卡，不浪费轮次。\n49. **改关卡预判须用最优配置的死亡数据** — 死亡分布做改关卡预判时，必须使用该档**当前最优配置**（WR 最接近目标的配置）的 failBucketDistribution。不同配置的死亡分布差异极大。用非最优配置的死亡数据触发改关卡判断是错误的——L81 案例：探针配置早期死亡 48%(WR=82.8%) 但最优配置早期死亡 0%(WR=85.2%)，前者本不该触发改关卡。
50. **AssetDatabase 缓存导致 tier 配置错乱** — Python `asset_patcher.write_ddc` 写 .asset 文件后，Unity batch mode 启动时可能用旧二进制缓存，导致 `DynamicDifficultyConfigs` 读取乱序（T1 读到 T5 的配置）。特征：所有档 WR 相同，CSV 中 startDifficulty 值错乱。修复：在 C# 入口 `BlastBotJenkinsBatchEntry.RunFromCommandLine` 加 `AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate)`。同步在 `BlastWorkbenchWindow.RunBotBatchByLevelRangeForJenkins` 循环前也加一道 `AssetDatabase.Refresh()`。不再需要 T1↔T5 互换 hack。

## Bot 默认局数

- **400**：入库验收（最终判定必用）
- **200（推荐）：** 中间探针轮，±3% 误差够判方向，节省一半时间
- 150：五槽位粗筛、宽谱探索

## 轮次上限

探针最多 6 轮（含首轮）。第 6 轮仍不合格则自动标记结论（⚠️ 接近 / ❌ 改关卡），不等待确认。全自动模式同样处理。

轮次仅消耗于有效运行：asset 未刷新等故障不消耗。

## 完整脚本索引

详见 level-optimizer 各 Step 标注。核心工具：
- `D:/download/Hermes/tools/get_level_pool.py` — 数据检索 (Step 1)
- `D:/download/Hermes/tools/design_probes.py` — 探针设计 (Step 2)
- `D:/download/Hermes/tools/asset_patcher.py` — asset 安全写入 (Step 3)
- `D:/download/Hermes/scripts/submit_batch_unity.py` — 批量提交+监控 (Step 3-5)
- `D:/download/Hermes/tools/judge_level.py` — 判级 (Step 6)
- `D:/download/Hermes/tools/find_best_combo.py` — 最佳组合搜索 (Step 6)

## 参考文档
| 文档 | 内容 |
|------|------|
| `references/judgment-rules.md` | 独立判定规则（数据源/合格判定/硬性违规/结果分级），流程外随时加载 |
| `references/probe-design.md` | 探针设计参考（需求驱动流程 + 调参经验 + 常见陷阱），设计探针时独立加载 |
| `references/probe-source-tagging.md` | 探针来源标注方法（按 sd/ratio 逐源匹配，不按 WR 段推断） |
| `references/multi-tier-opt-data-format.md` | Phase1 raw/reachability CSV 格式，解读方法 |
| `references/parameter-nonlinearity-lessons.md` | 四参数非线性经验（of/sc 响应曲线、实测数据） |
| `references/bot-batch-directory-structures.md` | bot 目录三种命名模式 |
| `references/data-retrieval-patterns.md` | 数据检索标准（3种目录模式+批量数据，BOM头处理） |
| `references/campaign-attempts-csv.md` | attempts CSV 字段说明 |