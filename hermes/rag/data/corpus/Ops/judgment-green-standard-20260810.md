# 判定标准 vs DB 颜色冲突：合格≠全绿（2026-08-10 用户裁定）

## 用户裁定：入库必须全绿（每档偏差 ≤10pp）

用户目标："我们的目的就是全绿"。auto_loop 判"合格"的关入库后 DB 前端显示黄关（偏差 10-15pp）——**判定标准与 DB 颜色标准脱节**，用户要求找人监督审查并修复。

## 根因（监督 agent 审查，reviews/judgment-vs-db-color-conflict-20260810.md）

不是 bug，是 **2026-08-05 的故意设计**：`rules.json` 的 `target_deviation` 被从 `{max:10, severity:near}` 改为 `{max:15, severity:hard}`（当时只对齐 DB 红字）。结果：
- **偏差 10-15pp 黄区完全不产生 reason → 判"合格"**，而 DB 前端是 ≤10🟢 / 10-15🟡 / >15🔴。
- 实测：L57 T3=64 vs 75（差11pp）、L147 T3=41.3 vs 30（差11.3pp）、L163 T4/T5=39.5 vs 50（差10.5pp）都在黄区仍判合格/接近入库。

## 关键事实

- **判定真源**：`judge_level.check_judgment()` 从 rules.json 读 `target_deviation.max`（现 15），dev>15 才硬违规。改 rules.json 一处全链路生效（judge_level/agent_review/auto_loop 都委托它）。
- **选档评分已偏好绿**：`target_pen_seg`（绿1/黄3/红8）无需改；问题只在判定门。
- **全绿 ≠ 合格**（反向）：L200 先例——全绿组合但 T4→T5 gap=2.5 仍不合格。合格 = gap 达标 + 偏差≤10 **两者都要**。

## 修复方案（2026-08-10 已落地：只做 A，B 被用户拒绝）

1. **A 判定收紧 ✅ 已实施**：`rules.json` `target_deviation.max` 15→10（judge_rules 下，severity 保持 hard）。合格 ⇒ 全绿；黄变不合格 → 下一轮。已同步：
   - `design_probes.py` RED=15→10（两处：L223 常量 + _expand_gradients 默认参）
   - `agent_review.py:43` >15→>10
   - 验证：`judge_level.py 57` → 不合格（T3=64 偏差 11pp>10）；L162 全档 ≤8.8pp 仍合格 ✅
2. **B 入库 gate ❌ 用户明确不做**：用户裁定"就A吧，**入库我来判定**"——不做 reimport 代码级全绿 gate，入库裁定权保留在用户。⚠️ 因此入库前 agent 必须**主动展示每档偏差颜色表**（≤10 绿/10-15 黄/>15 红）给用户裁定，不能只报"合格"。

## 物理可行性（落地时注意）

部分关 6 轮调不到 10pp（如 L163 T4/T5 天花板 ~45% vs 目标50）→ 走现有 6 轮改关卡机制，或人工调 Excel 目标；建议 auto_loop 待确认日志打印每档偏差+颜色辅助区分。

## 验证方法（已执行 ✅）

- `judge_level.py 57,147,163` 全变不合格（T3/T4 偏差 10.5-11.3pp >10）✅
- L162 全绿关仍合格（全档 ≤8.8pp）✅
- judgment-rules.md 已同步（见其"目标偏差约束"节）✅
