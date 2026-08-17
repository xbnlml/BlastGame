# 项目全面审计 2026-07-31（逐文件盘点）

用户要求的"逐文件全面审计"是重复出现的任务类（2026-07-30 有 audit_report.md，本次是第二次）。
输出格式约定：**每个文件标注状态（正常/需优化/废弃可删/可归档）+ 具体建议**，最后给跨文件不一致清单按 P0-P3 排优先级。只审计不改文件。

## 审计方法（可复用）

1. **全量清单**：`find . -type f -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/__pycache__/*'`（同时列目录树）
2. **分类读核心代码**：先读编排器（scripts/auto_loop.py）和 agent 入口（planner/warden/judge_level/curator），再读被 import 的库（asset_patcher、data/pool、get_level_pool），最后读 CLI 诊断工具。
3. **引用计数判状态**（关键技巧）：对系统权威 skill 做 `grep -c "<tool>" SKILL.md` + `grep -rl "<tool>" references/`：
   - 主文有引用 → 核心/在用
   - 仅 references 提到 → 遗留或手动诊断工具
   - 0 引用 → 孤儿/可归档候选
   - 再配合代码调用链 `grep -rln "<module>" tools/ scripts/ --include="*.py"`（排除 __pycache__）确认谁在 import 谁
4. **悬空引用 grep**：找文档/代码提到但文件不存在的引用（本次命中：`write_excel.py`、`submit_batch.py`、`progress.json`、multi-tier-designer 引用的 8 个缺失 reference 文件）
5. **一致性核对**：
   - board.md ↔ `_rounds.json` ↔ 最新 auto-log 尾部（rounds 文件是轮次真源；136 入库后 reset 属正常，board 滞后是常见问题）
   - rules.json ↔ judge_level/warden 代码（阈值是否硬编码、severity 是否一致）
   - MEMORY.md 铁则 ↔ 脚本实际行为（如 UNITY_EXE 动态读取 vs 硬编码）
   - 系统 skill ↔ 项目文件夹 skills/ 副本（diff 判定副本过期程度）
6. **数据目录抽查**：stage-data/_summary.json 的 updated_at、assets_backup 数量、auto-log 日期，判断工作数据是否新鲜。

## 文件状态矩阵（2026-07-31 快照）

### 新五角色体系核心 ✅
`tools/warden.py`、`tools/planner.py`、`tools/judge_level.py`、`tools/curator.py`、`tools/apply_probes.py`、`tools/design_probes.py`、`tools/agent_analyze.py`、`tools/asset_patcher.py`、`tools/get_level_pool.py`、`tools/dump_level_pools.py`、`tools/data/pool.py`、`tools/data/adapters/*`、`scripts/auto_loop.py`、`scripts/submit_batch_unity.py`、`tools/preflight.py`、`tools/retire_level.py`、`tools/post_batch_review.py`（source_tier bug 已修：`rec.get('source_tier', rec.get('tier',''))` 兼容）

### 保留（手动/诊断，非主流程）⚠️
`agent_data.py`（W06 签名校验依赖 + submit_batch_unity 独立模式 step4）、`agent_review.py`（auto_loop 不调，手动复核用）、`find_best_combo.py`、`postcheck.py`、`preflight.py`、`state_snapshot.py`、`diff_state.py`、`viz_level.py`、`read_target_wr.py`、`monitor_bot.py`（submit_batch_unity 已自监控，可归档）

### 废弃可删 ❌
`tools/.hermes-tmp.h10dwB`（0 字节临时）、`scripts/templates/`（空目录）、`stage-data/test_combo.json`（测试残留）、`tools/archive/check_unity.py` + `restart_unity.py`（系统 skill 明确禁用）、`tools/validate_combo.py`（独立 15pp 判定逻辑与 judge_level 三态不一致，早前审计就标记 legacy 未动）

### 可归档 📦
`tools/archive/` 其余 4 个、`project-state/_archive/`（write_excel.py 仍被项目 skill 副本引用——要么恢复要么改引用）、`daily-briefing/`、`ai_daily_report.txt`、`数值膨胀方案.xlsx` + `数值膨胀系统实现说明.md` + `play-on-offer-design.md`（经济系统工作流，与调优无关）、`.hermes/desktop-attachments/`

## ⚠️ 最大陷阱：项目内 skills/game-design/ 是过期副本

`D:\download\BlastGame\hermes\skills\game-design\` 下 6 个目录是合并进系统 `blastgame` skill **之前**的历史副本，Hermes 运行时不加载。内容多处与现行体系矛盾：
- `blastgame-level-optimizer` 仍写"三批流程（批A/批B/批C）"、引用已删的 `write_excel.py`、scripts/ 里躺着旧版 `submit_batch.py`（MEMORY.md 明确"已删除"）
- `blastgame-auto-pipeline` 无 SKILL.md，README 说"moved to _archive"但目录里没有 _archive（悬空）
- `blastgame-multi-tier-designer` 引用 8 个不存在的 reference 文件、仍写"4 轮上限"（现 6 轮）
- `blastgame-tier-debug` 与现行修复矛盾（称 AssetDatabase.Refresh 无效已废弃，但该修复已生效；称禁止写 $BLASTGAME_REPO，但 write_ddc 写 test/ asset 是授权操作）
- `blastgame-judgment` related_skills 引用不存在的 blastgame-probe-design

**铁则：审计/排障只认系统目录 `~/AppData/Local/hermes/skills/game-design/blastgame/`（含 26 个 references），项目副本一律不读不引用。** 建议整目录移入 project-state/_archive/。

## 漂移检查点（下次审计对照）

| 项 | 现状 | 建议 |
|---|---|---|
| UNITY_EXE 硬编码 6000.0.60f1 | auto_loop.py + submit_batch_unity.py 两处，与 MEMORY.md"必须从 ProjectVersion.txt 动态读取"矛盾 | 改代码或改记忆，二选一 |
| rules.json W03 severity=warn | warden/apply_probes 实际按 block 处理 | 统一为 block 或改代码 |
| judge_level.check_judgment 阈值硬编码 | `_load_rules()` 读了 rules.json 但判定函数未消费 | 让判定从 rules.json 取阈值 |
| curator 只更新 curator memory | planner/judge/warden memory 的"自动填充"区恒空 | 扩展 curator 回写范围 |
| stage_status.py 引用 progress.json | 文件不存在，悬空引用静默降级 | 删逻辑或补文件 |
| probe_configs.json 残留 24 关 | 大量已入库关配置残留，干扰手动排查 | 清理非 pending 关 |
| agents/*/memory.md "2025-07-31" | 日期笔误，应为 2026 | 顺手修正 |
| board.md / timeline.md 滞后 | 7-31 L136 已入库但 board 仍列需改关卡；timeline 停在 7-24 | auto_loop 跑完必须同步状态（现有铁则，审计时验证执行情况） |

## 状态文件真源（审计时的判定基准）

- 系统 skill：`~/AppData/Local/hermes/skills/game-design/blastgame/`（唯一权威）
- board.md = 关卡状态唯一源（但经常滞后，用 auto-log 最新日志交叉验证）
- `_rounds.json` = 轮次真源（合格/接近 reset 属正常，不报错）
- 手动挑配置记录.xlsx = 入库记录真源；lv_win_config_test.xlsx = 目标胜率真源
- MEMORY.md/USER.md = 用户偏好与铁则（注意去重：USER.md 大量重复条目、hermes/data/ 路径过时、blastgame profile 已废弃）
