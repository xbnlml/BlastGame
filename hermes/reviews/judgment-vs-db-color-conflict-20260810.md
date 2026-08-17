# 判定标准 vs DB 颜色标准冲突审查报告（2026-08-10）

> 结论先行：**冲突不是 bug，是 2026-08-05 的故意设计**——当时把 `target_deviation` 从 `{max:10, severity:near}` 改为 `{max:15, severity:hard}`，判定"不合格"只对齐 DB **红字**（>15pp），黄区（10-15pp）仍判"合格"。用户新目标"入库必须全绿（每档偏差 ≤10pp）"与现行 15pp 合格线矛盾。修复 = 判定收紧到 10pp（改 rules.json 一处）+ 入库前全绿硬 gate（reimport.py 加检查），并同步收紧探针规划红区（design_probes RED=15→10）。

---

## 一、根因：两套标准的阈值不一致

### 1.1 现行判定标准（代码事实）

`project-state/rules.json`（第 139-144 行，2026-08-05 改动）：

```json
"target_deviation": { "max": 15, "severity": "hard" },
"tolerance_pp": 2,
"near_tolerance_pp": 1
```

`tools/judge_level.py` `check_judgment()`（第 159-172 行）：
- 逐档算 `dev = |实测WR - Excel目标|`；
- `dev > 15pp` → 记 `硬性违规: 目标偏差超标` → **不合格**；
- `dev ≤ 15pp` → **完全不产生任何 reason** → 只要 gap 达标就判 **合格**。

**所以 10-15pp 黄区 = 合格。** 这就是 L57（T3=64 目标 75，差 11pp）、L147（T3=41.3 目标 30，差 11.3pp）判"合格"的直接原因（board.md 第 17/107 行实测确认）。

### 1.2 DB 前端颜色标准（前端事实）

`references/level-db-color-check-20260807.md`（第 32-36 行）+ `db-status-and-pool-full-data-20260807.md`（第 28 行）：

| 每档 \|实测-目标\| | DB 颜色 | 现行判定 | 用户目标 |
|---|---|---|---|
| ≤10pp | 🟢 绿 | 合格 | ✅ 可入库 |
| 10 < d ≤ 15pp | 🟡 黄 | **合格**（无 reason） | ❌ 不可入库 |
| >15pp | 🔴 红 | 不合格（硬性违规） | ❌ 不可入库 |

### 1.3 为什么 2026-08-05 会定 15pp

`SKILL.md` 第 196-197 行记录了当时的用户裁定：「gap 小于 5 或者**红了**就标不合格」——即只要求"红字 = 不合格"，黄区有意放行。`target-deviation-20260731.md` 也写明最初是 `{max:10, severity:near}`（超标降"接近"）。**改 15 的动机是让判定与 DB 红字对齐，但由此造成了"黄字=合格"的缺口。** 用户 08-10 的新目标（入库全绿）实质是把这个缺口补上：合格线从 15 收紧到 10。

---

## 二、标准对比表（全链路）

| 环节 | 文件/函数 | 现行阈值 | 与"全绿"的关系 |
|---|---|---|---|
| 选档评分 | `find_best_combo.py` `target_pen_seg` | 绿≤10（斜率1）/ 黄10-15（斜率3）/ 红>15（斜率8） | 已按绿<黄<红排序，**无需改**（评分已偏好绿组合） |
| 选档硬过滤 | `find_best_monotonic` 枚举 | 只查单调 + gap∈[4,40]，无偏差硬门 | 可能选出黄组合（池内无绿时）→ 判定阶段拦截 |
| 判定 | `judge_level.check_judgment` | `target_deviation.max=15, severity=hard` | **冲突点①：黄也判合格** |
| 判定容差 | `rules.json tolerance_pp=2` | 只作用于 gap 合格线（`ok_lo-2`），不作用于偏差 | 与全绿无冲突 |
| 探针规划 | `design_probes.py` `RED=15`（223/271 行）+ 可达性预检（544-547 行） | 探针目标带 = 目标 ±15pp；距天花板>15pp 建议改关卡 | **冲突点②：会继续打 11-15pp 的"注定黄"的探针，浪费轮次** |
| agent 复核 | `agent_review.py` `check_targets`（43 行） | `abs(diff)>15` 才算 issue | 冲突点③：黄档不报 |
| 入库 | `reimport.py` | **无任何偏差检查**，给什么写什么 | 冲突点④：DB 端无最后防线 |
| 6 轮机制 | `judge_level.judge_with_rounds` | 不合格 → r+1；6 轮 → 改关卡 | 收紧后成为"物理不可达关"的出口 |
| DB 显示 | LevelDatabase/Run/test.json 前端 | ≤10 绿 / ≤15 黄 / >15 红 | 用户要求最终状态全绿 |

---

## 三、修复方案（推荐 A+B 都做）

### 方案 A：判定收紧——"合格"必须全绿（主修复）

**改 `project-state/rules.json` 一处**（第 139-142 行）：

```json
"target_deviation": { "max": 10, "severity": "hard" }
```

- `judge_level.check_judgment` 读 rules.json，**自动生效**，代码零改动：dev>10pp → 硬性违规 → 不合格；合格 ⇒ 每档偏差 ≤10pp ⇒ 全绿。黄区不再判合格。
- `agent_review.check_gaps` 委托 `check_judgment`，自动生效。
- `auto_loop` Phase5（`scripts/auto_loop.py` 766 行 `result in ('合格','接近')`）自动生效：黄组合不再进 `passed` 待确认，改为下一轮。
- 注意 `judge_with_rounds` 中"接近 → 入库(接近)"路径（judge_level.py 230-232 行）：收紧后"接近"只可能来自 **gap 接近带**（偏差已全绿），DB 显示仍全绿，语义自洽，可保留；若用户连 gap 接近也不想要，把 `action='入库(接近)'` 改成 `下一轮` 即可（可选）。

**同步收紧探针规划（防浪费轮次）**：
- `tools/design_probes.py`：`RED = 15` → `10`（223 行、271 行默认参数）；可达性预检 544-547 行 `>15` → `>10`（"距天花板>10pp 建议改关卡"）。
- `tools/agent_review.py` 43 行：`abs(diff) > 15` → `> 10`。
- `find_best_combo.py` `target_pen_seg` 不用改（黄段斜率 3 已劣于绿段斜率 1；黄组合仍可能被选出，但会正确判不合格 → 下一轮，属于正常行为）。

### 方案 B：入库前全绿硬 gate（DB 端最后防线，推荐必做）

**改 `tools/reimport.py`** `reimport()`（135 行起，每关循环开头）：读 Excel 目标（`et.get_target(lv)`），逐档算 `|wr-targets[i]|`，任一 >10pp → 记 `FAIL: T{i+1} 偏差 X.Xpp > 10pp (黄/红)，拒绝入库` 并 `continue`，不落盘。

```python
from tools.data.adapters import excel_target as et
t = et.get_target(lv)
if t and t.get('tiers'):
    bad = [f"T{i+1}:{cfg['tiers'][i]['wr']:.1f} vs {t['tiers'][i]:.0f} (差{abs(cfg['tiers'][i]['wr']-t['tiers'][i]):.1f}pp)"
           for i in range(min(5, len(cfg['tiers'])))
           if abs(cfg['tiers'][i]['wr'] - t['tiers'][i]) > 10]
    if bad:
        results.append((lv, 'FAIL', '非全绿拒绝入库: ' + '; '.join(bad)))
        continue
```

- 作用：即使上游（auto_loop 判定、人工改 config JSON）放行了黄组合，DB 也写不进去——把用户目标"入库必须全绿"变成**代码级保证**，而不是口头约定。
- `--dry-run` 时也打印该检查结果，便于确认前预览。

### 方案 C（不推荐单独用）：只加 gate 不改判定

auto_loop 会继续把黄组合标"合格"、浪费 6 轮调参周期，直到 6 轮后才改关卡；且 gate 拦截发生在确认入库时，用户体验差。**判定收紧（A）负责"别浪费轮次"，gate（B）负责"DB 永不全黄"，两者职责互补，都做。**

---

## 四、物理可行性：收紧后会不会"永远不合格"？

会有一部分关 6 轮调不到 10pp 内，但这是**预期行为**，且现有机制已有出口：

1. **牌面物理天花板不可达**（如 L85 T1 目标 90%、实测最高 81.2%；L163 T4/T5 目标 50、实测 39.5-45%）：10pp 不可达 → 6 轮后 `改关卡`（现有流程，`retire_level` + 改关卡方向判断）。这正是用户要的：**入库全绿 = 达不到的关不许进库，必须改关卡**。
2. **Excel 目标本身定得不合理**（人工目标超出关卡可实现范围）：收紧后同样走改关卡，但正确做法是**人工调 Excel 目标**（目标是设计意图，前端颜色相对目标计算）。建议在 auto_loop Phase5 待确认日志里打印**每档偏差+颜色**（如 `T3: 64.0 vs 75 (黄 -11.0pp)`），帮用户区分"目标不可达"还是"配置没找对"。
3. **黄区例外路径保留**：历史上有"黄区用户裁定入库"先例（L110 T1/T2 76.9 黄区，用户明确裁定入库）。收紧后若仍要人工放行黄关，走 gate 的显式跳过（如 config JSON 加 `"allow_yellow": true` 字段，gate 检查到该字段时打 ⚠ 警告放行）——**人工显式覆盖 ≠ 自动合格**，不违背用户目标。

---

## 五、改动清单（全部文件+位置）

| # | 文件 | 位置 | 改动 |
|---|---|---|---|
| 1 | `project-state/rules.json` | `judge_rules.target_deviation.max` | 15 → **10**（severity 保持 hard） |
| 2 | `tools/design_probes.py` | 223 行 `RED = 15`、271 行默认参、544-547 行可达性预检 | 15 → **10** |
| 3 | `tools/agent_review.py` | 43 行 `abs(diff) > 15` | 15 → **10** |
| 4 | `tools/reimport.py` | `reimport()` 循环开头 | 新增全绿 gate（见方案 B 代码） |
| 5 | `scripts/auto_loop.py` | Phase5 待确认日志（797 行附近） | 打印每档偏差+颜色（可选，辅助人工确认） |
| 6 | 文档同步 | skill `references/judgment-rules.md`（46 行写的是 max:10/near，已过期）、`target-deviation-20260731.md`、`balanced-scoring-20260805.md` | 更新为 max:10/hard + 全绿语义 |

**不需要改**：`judge_level.py`（读 rules.json，自动生效）、`find_best_combo.py`（评分已绿<黄<红）、`planner.py`（委托 judge_level/design_probes）、`tools/data/pool.py`。

---

## 六、验证建议

1. 改完 rules.json 后跑 `python tools/judge_level.py 57,147,163`：应全部从"合格/接近"变为"不合格"（reason 含 `目标偏差超标`）。
2. 跑 `python tools/find_best_combo.py 57` 确认最优组合的黄档（T3/T4/T5 64/49/49 vs 75/60/60）仍被选出但判不合格——证明选择与判定解耦正常。
3. 找一关当前全绿的（如 L162 65.8/55.2/36.0/26.4/11.2 vs 70/55/40/30/20），确认收紧后仍判合格，无回归。
4. 用 `--dry-run` 跑一次 reimport，确认 gate 在黄关上报 FAIL、绿关正常通过。
