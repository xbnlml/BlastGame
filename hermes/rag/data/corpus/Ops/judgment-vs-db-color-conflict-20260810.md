# 判定标准 vs DB 颜色标准冲突（2026-08-10 审查）

> 场景：auto_loop 判"合格"的关入库后，DB 前端（LevelDatabase/Run/test.json 中控）显示黄关（偏差 10-15pp）。
> 结论：**不是 bug，是 2026-08-05 故意设计**——target_deviation max=15 只对齐 DB 红字（>15pp 不合格），黄区（10-15pp）无 reason 判合格；与用户 08-10 新目标"入库必须全绿（每档偏差≤10pp）"冲突。
> 状态：**只读审查，修复待实施**。完整报告：`hermes/reviews/judgment-vs-db-color-conflict-20260810.md`。

## 根因（代码事实）

- `project-state/rules.json` `judge_rules.target_deviation = {max:15, severity:hard}`（2026-08-05 从 `{max:10, severity:near}` 改来，当时用户裁定"红了才标不合格"）。
- `judge_level.check_judgment()`（159-172 行）逐档算 `|实测-目标|`：>15pp → 硬性违规不合格；≤15pp → 不产生任何 reason → gap 达标即"合格"。
- DB 前端颜色（`level-db-color-check-20260807.md`）：≤10🟢 / 10<d≤15🟡 / >15🔴，按每档偏差算，与 gap 无关。
- 实测例（board.md）：L57 T3=64 vs 75（差11pp）、L147 T3=41.3 vs 30（差11.3pp）→ 黄区仍判合格/接近入库。

## 修复方案（A+B 都做）

1. **A 判定收紧（主修复）**：rules.json `target_deviation.max` 15→10（severity 保持 hard）。`check_judgment` 读 rules.json → judge_level / agent_review.check_gaps / auto_loop Phase5 全部自动生效，**代码零改动**。合格 ⇒ 每档偏差≤10pp ⇒ 全绿。
2. **B 入库 gate（DB 端防线）**：`reimport.py` `reimport()` 每关循环开头加全绿检查（`|wr-目标|>10pp` → FAIL 拒绝落盘，不写 asset/Excel/board）。防人工 config 放行黄关；可留 `allow_yellow` 显式人工覆盖字段（L110 黄区裁定入库先例）。
3. **同步收紧探针规划（防浪费轮次）**：`design_probes.py` RED=15→10（223/271/544-547 行，"距天花板>10pp 建议改关卡"）；`agent_review.py:43` `abs(diff)>15`→`>10`。
4. **不用改**：`find_best_combo.target_pen_seg`（绿斜率1/黄3/红8 已偏好绿组合，黄组合会被判定拦截）、`planner.py`、`tools/data/pool.py`。

## 关键认知

- **全绿 ≠ 合格**：合格 = gap 达标（分档标准/目标档位差）+ 每档偏差≤10pp 两者都要。L200 先例：全绿组合 [58.5,40.5,26.4,19.6,17.1] 偏差全≤8.5 但 T4→T5 gap=2.5 仍不合格。
- **判定单一真源 = rules.json + judge_level.check_judgment()**；skill 里 judgment-rules.md 等文档可能过期（judgment-rules.md 还写 max:10/near），以 rules.json 为准。
- **收紧后的物理可行性**：部分关 6 轮调不到 10pp（牌面天花板，如 L85 T1 目标90% 实测最高81.2%；L163 T4/T5 目标50 实测39.5-45%）→ 走现有 6 轮改关卡机制（预期行为），或人工调 Excel 目标（目标是设计意图，前端颜色相对目标计算）。auto_loop 待确认日志应打印每档偏差+颜色帮助区分。
- **"接近"路径**：收紧后 `judge_with_rounds` 的"接近→入库(接近)"只剩 gap 接近带触发（偏差已全绿），DB 显示仍全绿，语义自洽；若用户连 gap 接近也不想要，改 action 为"下一轮"。

## 验证清单（改完后）

1. `python tools/judge_level.py 57,147,163` → 应全变"不合格"（reason 含 目标偏差超标）。
2. L162（65.8/55.2/36.0/26.4/11.2 vs 70/55/40/30/20，全绿）→ 仍判合格，无回归。
3. `reimport.py --dry-run` → 黄关报 FAIL，绿关正常通过。
