# BlastGame Hermes 项目全面审计报告

**日期：** 2026-07-30  
**审计范围：** `<HERMES_ROOT>` 全部 tools/、scripts/、skills/、project-state/

---

## 一、多 Agent 工作流总览

```
agent_data.py ──→ 刷新 stage-data 数据池 + level_sig 校验
agent_analyze.py ──→ filter_verified + find_best_monotonic + 探针设计
agent_review.py ──→ 四元组校验 + check_gaps(judge_level) + Excel交叉
judge_level.py ──→ 按 blastgame-judgment 标准 + 6轮追踪
submit_batch_unity.py ──→ 链入 agent pipeline (analyze → review)
```

---

## 二、tools/ 逐文件审计

### ✅ 已覆盖（被 agent pipeline 直接或间接调用）

| 文件 | 调用链 | 状态 |
|------|--------|------|
| `agent_data.py` | 自身是 agent | ✅ |
| `agent_analyze.py` | 自身是 agent | ✅ |
| `agent_review.py` | 自身是 agent | ✅ |
| `judge_level.py` | agent_review → `check_judgment()`; 读写 `_rounds.json` | ✅ |
| `asset_patcher.py` | agent_data(level_sig, verify_integrity), agent_review(read_ddc), submit_batch_unity(verify_all) | ✅ |
| `data/pool.py` | agent_analyze(filter_verified, find_best_monotonic, dedup_records), judge_level, post_batch_review | ✅ |
| `data/adapters/excel_target.py` | agent_analyze(get_target), agent_review(get_target), judge_level(get_difficulty) | ✅ |
| `get_level_pool.py` | agent_data(parse_levels), dump_level_pools(build_level_pools) | ✅ |
| `dump_level_pools.py` | agent_data(refresh_pools), submit_batch_unity(step 4) | ✅ |
| `__init__.py` | 包标记 | ✅ |

### ⚠️ 重复 / 功能重叠

| 文件 | 问题 | 建议 |
|------|------|------|
| `find_best_combo.py` | 与 `agent_analyze.py` 功能重叠——都调用 `pool.find_best_monotonic()`。find_best_combo 是 CLI 工具（含死亡分布展示），agent_analyze 是程序化路径。 | ⚠️ 保留作为手动诊断工具，但核心逻辑已在 pool 层统一。无需修复。 |
| `validate_combo.py` | 有自己的 `validate()` 函数，**不使用 judgment-rules.md 标准**，与 `judge_level.py` + `agent_review.py` 判定体系不一致。判定逻辑独立且宽松（15pp档差底线 vs 标准5pp硬违规）。 | ⚠️ 建议合并到 judge_level 体系，或标记为 legacy。 |
| `archive/pick_best_combos.py` | 与 `find_best_combo.py`/`agent_analyze.py` 重叠，硬编码 172-184 关卡。 | ⚠️ 已在 archive/，保持。 |

### ❌ 遗漏（未被 agent pipeline 调用）

| 文件 | 问题 | 建议 |
|------|------|------|
| **`design_probes.py`** | ❌ **未被 agent_analyze 调用。** agent_analyze 有内联 `_design_probes()` 函数（约40行），与 design_probes.py（164行，含 bot400 baseline 评估、phase2 候选排序）**逻辑不同且更简陋**。design_probes.py 有更成熟的探针设计逻辑但被绕过。 | **高优先级修复：** agent_analyze 应调用 `design_probes.design(lv)` 替代内联简化版，或至少合并逻辑。内联版缺少 bot400 baseline 评估、phase2 候选评分、优先 in-range 排序等功能。 |
| `apply_probes.py` | ❌ **不在 agent pipeline 中。** 写 asset 配置是 agent pipeline 的前提步骤，但目前 agent 流程假设 asset 已预先配置好。 | 建议在 agent pipeline 前加一步：agent_data → apply_probes → submit_batch_unity。或将 apply_probes 逻辑整合到 agent_data。 |
| `probe_configs.json` | ❌ **不被 agent 读写。** design_probes.py 写它，apply_probes.py 读它。agent_analyze 的内联探针设计不持久化。post_batch_review.py 读它做对比但 agents 不。 | 需要 agent_analyze 输出探针到 probe_configs.json，或 agent pipeline 中加 apply_probes 步骤。 |
| `monitor_bot.py` | ❌ **不被 agent pipeline 调用。** submit_batch_unity.py 自己监控 Unity 输出。monitor_bot.py 是轮询 bot 目录的独立工具。 | 如果 submit_batch_unity 已覆盖监控功能，可归档。否则集成到 pipeline。 |
| `read_target_wr.py` | ❌ **不被 agent 调用。** Agents 通过 `data/adapters/excel_target.py` 读 Excel 目标。 | 📦 可归档或保留为手动诊断工具。 |
| `asset_patcher.py::verify_all()` | ❌ **agent_data 不调用 verify_all()。** agent_data 只调单个 `verify_integrity(lv)`。submit_batch_unity 在 step 0a 调 verify_all，但 agent pipeline 独立运行时不会触发。 | 建议 agent_data 加 `--verify-all` 选项。 |

### 📦 可归档（运维/诊断工具，不参与核心流程）

| 文件 | 用途 | 建议 |
|------|------|------|
| `check_unity.py` | 检查 Unity 是否运行 | 📦 skill 明确禁止主动调，可归档 |
| `restart_unity.py` | 启动/重启 Unity | 📦 skill 明确禁止主动调，可归档 |
| `diff_state.py` | 对比 asset vs Excel vs pool | 📦 诊断工具，保留但不需要 agent 覆盖 |
| `state_snapshot.py` | 全局状态快照（读 board.md + pool） | 📦 诊断工具，保留 |
| `stage_status.py` | 51-200 状态汇总 | 📦 诊断工具，保留 |
| `viz_level.py` | Plotly 可视化 | 📦 诊断工具，保留 |
| `archive/check_excel_wr.py` | 已归档 | 📦 |
| `archive/compare_pool_data.py` | 已归档 | 📦 |
| `archive/verify_excel_wr.py` | 已归档 | 📦 |

### ⚠️ 手动流程工具（skill 引用但非 agent 调用）

| 文件 | 调用场景 | 状态 |
|------|---------|------|
| `preflight.py` | skill 三批流程的批A步骤1 | ⚠️ 不在 agent pipeline 中，但 submit_batch_unity 有内联 asset 校验。建议 agent pipeline 加 preflight 检查。 |
| `postcheck.py` | skill 入库/改关卡后验证 | ⚠️ 手动流程工具。agent_review 部分覆盖了验证逻辑（四元组+gap+Excel），但缺少 snapshot 备份、board 总数校验。 |
| `retire_level.py` | skill 改关卡流程 | ⚠️ 手动工具。agent pipeline 不覆盖改关卡场景（agent 流程是自动化的，改关卡是人工决策）。 |
| `post_batch_review.py` | submit_batch_unity step 5 | ⚠️ **已串联但存在 bug（见下方）** |

---

## 三、scripts/submit_batch_unity.py 审计

### Agent Pipeline 串联情况

submit_batch_unity.py 的步骤链：
1. **Step 0a:** asset 完整性验证（`verify_all`） ✅
2. **Step 4:** 刷新池子（`dump_level_pools`） ✅
3. **Step 5:** 批后分析（`post_batch_review`） ⚠️ 有 bug
4. **Step 6:** Agent pipeline（`agent_analyze` → `agent_review`） ✅

### 缺失环节

- ❌ **无 agent_data 调用。** agent_data 负责刷新池子+level_sig 校验，submit 脚本只调了 dump_level_pools。建议 step 4 替换为 agent_data。
- ❌ **无 design_probes 调用。** 组合分析后不自动设计下轮探针。
- ❌ **无 apply_probes 调用。** 不自动写入 asset 配置。
- ❌ **无 preflight 调用。** 依赖内联 asset 校验，缺少 board 冲突检查、Editor 冲突检查、数据源预览。

---

## 四、project-state/ 文件审计

| 文件 | 读写者 | Agent 覆盖 |
|------|--------|-----------|
| `board.md` | preflight.py(R/W), postcheck.py(R), state_snapshot.py(R), retire_level.py(R/W) | ❌ **无 agent 读/写。** 状态变更（入库/改关卡）应自动更新 board.md。 |
| `timeline.md` | 手动维护，skill 要求手动更新 | ❌ **无 agent 读/写。** 建议 agent 完成后自动追加事件记录。 |
| `_rounds.json` | judge_level.py (R/W): `_load_rounds()`, `_save_rounds()`, `inc_round()`, `reset_round()` | ✅ **已覆盖。** agent_review 委托 judge_level，间接读写。 |
| `wrongbook.md` | 无代码引用 | ❌ 未被任何代码读取。 |

---

## 五、.hermes-blastgame/skills/ 审计

### blastgame-level-optimizer (SKILL.md v7.2.0)

| 引用的工具 | Agent 覆盖 | 状态 |
|-----------|-----------|------|
| preflight.py | ❌ | 手动流程 |
| postcheck.py | ❌ | 手动流程 |
| retire_level.py | ❌ | 手动流程 |
| asset_patcher.py | ✅ | agent_data, agent_review |
| dump_level_pools.py | ✅ | agent_data, submit |
| find_best_combo.py | ⚠️ | 被 agent_analyze 替代 |
| post_batch_review.py | ⚠️ | 在 submit 中调用但有 bug |
| submit_batch_unity.py | ✅ | 主入口 |
| judge_level.py | ✅ | agent_review 委托 |
| design_probes.py | ❌ | agent_analyze 有内联版但更简陋 |
| apply_probes.py | ❌ | 不在 pipeline 中 |

### blastgame-judgment (SKILL.md v1.0.0)

| 引用 | Agent 覆盖 | 状态 |
|------|-----------|------|
| judgment-rules.md | ✅ | judge_level.check_judgment() 实现 ②③④⑤ |
| gap-scoring.md | ✅ | pool._gap_score() 实现 |
| 数据源优先级 | ✅ | pool._source_penalty(), filter_verified() |

### blastgame-multi-tier-designer (SKILL.md v3.5.0)

| 引用 | Agent 覆盖 | 状态 |
|------|-----------|------|
| probe-design.md | ❌ | agent_analyze 内联探针未使用这些规则 |
| judgment-rules.md | ✅ | 通过 judge_level |
| 探针设计原则 | ❌ | agent_analyze._design_probes() 不遵循 skill 的需求驱动流程 |

---

## 六、具体项检查

### 1. design_probes.py 是否被 agent_analyze 或 submit 调用？
❌ **否。** agent_analyze 有内联 `_design_probes()`（40行简化版），但从未 import design_probes。submit_batch_unity 也不调用它。design_probes.py（164行）有更成熟的逻辑：bot400 baseline 评估、phase2 候选排序、优先 in-range 候选等。

### 2. preflight.py / postcheck.py 是否仍被调用？
⚠️ **仅被 skill 手动流程引用**，不被 agent pipeline 调用。submit_batch_unity 有内联 asset 校验，但不包含 preflight 的完整检查（board 冲突、Editor 冲突、数据源预览）。postcheck 的 Excel vs Asset 一致性、snapshot 备份检查在 agent pipeline 中缺失。

### 3. post_batch_review.py 是否修复了 source_tier bug？
❌ **未修复。** 第162行：
```python
for rec in sorted(batch_recs, key=lambda x: int(x['source_tier'][1:]) if x.get('source_tier','').startswith('T') else 0):
    r_tier = rec['source_tier']
```
但第119行的 records 使用 key `'tier'` 而非 `'source_tier'`。这会导致 KeyError 或排序全部归零。应改为：
```python
for rec in sorted(batch_recs, key=lambda x: int(x['tier'][1:]) if x.get('tier','').startswith('T') else 0):
    r_tier = rec['tier']
```

### 4. agent_review.py check_gaps 是否委托给了 judge_level？
✅ **是。** 第26-28行：
```python
from tools.judge_level import check_judgment
result, issues = check_judgment(combo, difficulty)
return [] if result == '合格' else issues
```
正确使用了 judgment-rules.md 标准（②合格判定 + ③硬性违规 + ④档差审美 + ⑤结果分级）。

### 5. find_best_combo.py / pick_best_combos.py 是否有重复？
⚠️ **功能重叠。** 三者的核心都是调用 `pool.find_best_monotonic()`：
- `find_best_combo.py`：通用 CLI，含死亡分布展示，读 Excel 目标
- `pick_best_combos.py`（archive/）：硬编码 172-184 关卡，自实现去重逻辑（不调用 pool.dedup_records）
- `agent_analyze.py`：程序化路径，filter_verified + find_best_monotonic，JSON 输出

建议：find_best_combo.py 保留为手动诊断工具，pick_best_combos.py 已在 archive 中无需操作。

### 6. apply_probes.py / probe_configs.json 是否在流程中有位置？
❌ **不在 agent pipeline 中。** 
- `probe_configs.json` 被 design_probes.py 写入、apply_probes.py 读取、post_batch_review.py 读取做对比
- 但 agent pipeline（agent_analyze → agent_review → submit）不读不写 probe_configs.json
- agent_analyze 的内联探针设计结果不持久化

### 7. dump_level_pools.py / get_level_pool.py 是否被 agent_data 覆盖？
✅ **是。** agent_data.py 第14-15行：
```python
from tools.get_level_pool import parse_levels
from tools.dump_level_pools import build_level_pools, dump_all_pools
```
agent_data.refresh_pools() 封装了 build_level_pools + dump_all_pools。

### 8. validate_combo.py / check_unity.py / restart_unity.py / retire_level.py 是否该归档？
- **validate_combo.py**：⚠️ 有独立判定逻辑，与 judge_level 标准不一致。建议合并或标记 legacy。
- **check_unity.py**：📦 可归档。Skill 明确禁止主动调用。
- **restart_unity.py**：📦 可归档。Skill 明确禁止主动调用。
- **retire_level.py**：⚠️ 保留。改关卡是人工决策，不在自动 agent pipeline 范围内，但需要手动执行。

### 9. diff_state.py / state_snapshot.py / stage_status.py / viz_level.py 的用途
| 工具 | 用途 | 建议 |
|------|------|------|
| `diff_state.py` | 对比 asset vs Excel vs pool 三方一致性 | 📦 诊断工具，保留 |
| `state_snapshot.py` | 一行一关的全局快照（WR/gap/死亡分布） | 📦 诊断工具，保留 |
| `stage_status.py` | 51-200 完成/待处理/无数据汇总 | 📦 诊断工具，保留 |
| `viz_level.py` | Plotly 散点图/span 分布图 | 📦 诊断工具，保留 |

---

## 七、汇总统计

| 状态 | 数量 | 说明 |
|------|------|------|
| ✅ 已覆盖 | 13 | agent + core libs + data adapters |
| ⚠️ 重复/重叠 | 4 | find_best_combo, validate_combo, pick_best_combos, post_batch_review(bug) |
| ❌ 遗漏 | 6 | design_probes, apply_probes, probe_configs.json, monitor_bot, read_target_wr, asset verify_all |
| 📦 可归档 | 8 | check_unity, restart_unity, diff_state, state_snapshot, stage_status, viz_level + archive/* |

---

## 八、修复优先级

### 🔴 P0 — 阻断性 Bug
1. **post_batch_review.py source_tier bug**：第162行 `source_tier` → `tier`，否则批后分析排序/显示崩溃。

### 🟠 P1 — Agent Pipeline 缺口
2. **agent_analyze 应调用 design_probes.py**：内联 `_design_probes()` 过于简陋，缺少 bot400 baseline、phase2 候选评分、in-range 优先排序。
3. **agent pipeline 缺少 apply_probes 步骤**：探针设计结果应持久化到 probe_configs.json 并写入 asset。
4. **submit_batch_unity 应调用 agent_data 替代裸 dump_level_pools**：确保 level_sig 签名校验在刷新时执行。
5. **agent pipeline 缺少 preflight 检查**：submit 的内联校验缺少 board 冲突、Editor 冲突、数据源预览。

### 🟡 P2 — 状态追踪
6. **agent 应更新 board.md**：入库/改关卡后自动更新状态和 timeline.md。
7. **project-state/ 文件未被 agent 读写**：board.md、timeline.md、wrongbook.md 均缺失 agent 集成。

### 🟢 P3 — 清理
8. **validate_combo.py 合并或归档**：判定标准与 judge_level 不一致。
9. **check_unity.py / restart_unity.py 归档**：skill 明确禁止使用。
