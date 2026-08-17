---
name: blastgame-judgment
description: "BlastGame 多档位判定规则——数据源核实、合格判定、硬性违规、档差审美、结果分级。裁定场景加载，不包含探针设计。"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [blastgame, game-design, judgment, rules]
    related_skills: [blastgame-level-optimizer, blastgame-probe-design]
---

# BlastGame 多档位判定规则

> **裁定场景专用。** 加载此 skill 时立即加载 `references/judgment-rules.md` 作为判定依据。

## 判定全流程（5 步，缺一不可）

每步没通过就停在当前步，不要跳下一步。

### ① 数据源核实

判定前必须确认每条数据的来源和局数。优先级：**局数优先，同局数再按来源比**。

`_source_penalty` 公式：
```
games_tier × 5 + source_rank
  bot≥400=0    bot=0
  300-399=1    summary=1
  200-299=2    phase0=2
  <200=3       phase2=3
               phase1=4
```

| 数据 | 局数 | 来源 | 罚分 |
|------|------|------|------|
| bot | ≥400 | bot | 0×5+0 = **0** |
| summary | ≥400 | summary | 0×5+1 = **1** |
| phase0 | 300-399 | phase0 | 1×5+2 = **7** |
| bot | 300-399 | bot | 1×5+0 = **5** |
| phase2 | 200-299 | phase2 | 2×5+3 = **13** |
| bot | 200-299 | bot | 2×5+0 = **10** |
| phase1 | <200 | phase1 | 3×5+4 = **19** |

此罚分在所有决策点统一使用（去重、桶排序、组合质量分）。

**铁律：** `find_best_monotonic` 传全部 `recs`，**不预过滤数据源**。`dedup_records` 自动按优先级处理。

### ② 合格判定（逐档算）

```
Normal:   T1→T3 ≥ 15pp, T3→T5 ≥ 15pp, T3 ≥ 60%
Hard:     各档差 ≥ 10pp, T3 ∈ [30%, 60%]
SuperHard: 各档差 ≥ 10pp, T3 ≤ 50%
```

**偏离 ≤2pp 直接合格。** Normal 不设 gap>40% 上限。

### ③ 硬性违规（任一条即不合格）

- 任意相邻档差 < 5%
- 任意相邻档差 > 40%（仅 Hard/SuperHard）
- 倒挂超 1%（低档 WR > 高档 WR）
- Normal T3 < 60%
- 任意档 WR < 5%
- <10% 档 > 1 个

### ④ 档差审美（推荐，非强制）

```
>50% 段: 15-35pp 可接受（最优 20-30pp）
<50% 段: 5-25pp 可接受（最优 10-20pp）
递减: 高段 > 低段，低段超过高段 ≤4pp 允许
```

### ④a gap 罚分（`_gap_score`，品质分用）

`find_best_combo` 内部用连续罚分评价 gap 质量，优先于目标接近度：

```python
if g < 15:
    score += (15 - g) * 5   # 基本：每缺 1pp = 5 分
if g < 10:
    score += (10 - g) * 10  # 额外：gap<10 再加一层
```

**罚分速查：**
| gap | 基本 | 额外 | 总罚分 |
|-----|------|------|--------|
| 15pp | 0 | 0 | **0** |
| 14pp | 5 | 0 | **5** |
| 12pp | 15 | 0 | **15**（≈ 每档离目标 5%） |
| 10pp | 25 | 0 | **25** |
| 8pp | 35 | 20 | **55** |
| 5pp | 50 | 50 | **100** |

gap<10 时额外加罚，gap=10-15 时线性递减。边界连续无跳变。

### ④b 品质分权重

```python
q = target_score + source_score × 0.3 + gap_score + death_score
```

`source_score` 权重压低（×0.3），防止局数/来源优势压倒 WR 差距。gap 罚分权重等于目标差罚分，gap<10 时 gap 优先。

### ⑤ 结果分级 + 死亡分布改关卡预判

- ✅ **合格** → 入库
- ⚠️ **接近**（各档差偏离 ≤2pp，或 WR 离目标 ≤5pp）→ 标记待确认，不做改关卡
- ❌ **不合格** → 下一轮 / 第6轮仍不合格 → 改关卡

**死亡分布改关卡预判（T1/T2 目标≥60% 时检查）：**
```
最佳组合 T1 的 deathProfile 中 earlyDeath（桶 0-1 和）> (1 - 目标WR) × 80%
→ 直接标记改关卡，不走 6 轮
```
此规则嵌入 find_best_combo 的死亡分析输出中，不独立判断。

## 诊断核心规则

### 递减违规诊断流程（常见错误）

**先逐档对标目标差，再分析 gap。** 递减是表象，根因是哪档离目标最远。

```
错误路径：看到递减违规 → 默认压 T3/抬 T5 → 方向反了
正确路径：逐档算目标差(T1±pp T3±pp T5±pp) → 标记偏差最大的档 → 打偏差档
例：L89 92/76/27 目标 90/75/60 → T5:-33pp 是根因 → 探T5抬(不是压T3)
    L91 98/82/55 目标 90/75/60 → T3:+7pp 是根因 → 探T3压(不是抬T5)
```

### 数据源检视（致命错误）

**下结论前看全量池子，不止看 bot400。**

```python
recs = pool.dedup_records(pool.get_preferred_records(str(LV)))
n_bot = sum(1 for r in recs if r['source']=='bot' and r['totalGames']>=400)
n_sum = sum(1 for r in recs if r['source']=='summary' and r['totalGames']>=400)
n_ph = sum(1 for r in recs if r['source'] in ('phase2','phase1'))
print(f'bot400={n_bot} sum400={n_sum} phase={n_ph}')
```

这条命令在 `preflight.py submit` 的数据源预览中也已包含。

### 数据来源标注（展示时必做）

每行数据必须标注来源（bot400 / summary400 / phase2 等），严禁裸写 WR 不标来源。

## 判定前加载

```bash
skill_view(name="blastgame-judgment", file_path="references/judgment-rules.md")
skill_view(name="blastgame-judgment", file_path="references/gap-scoring.md")
```
