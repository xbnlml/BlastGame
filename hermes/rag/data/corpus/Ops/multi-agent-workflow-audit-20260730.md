# 多 Agent 工作流完整性审计（2026-07-30）

对 `tools/agent_data.py`、`tools/agent_analyze.py`、`tools/agent_review.py` 三个 agent 脚本的全面审查。

## 审计结论：❌ FAIL — 存在关键缺口

### ✅ PASS（3项）

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | `--help` 输出完整性 | ✅ 三个 agent 参数完整，agent_review 使用 `--combo-file` 符合职责 |
| 2 | `--levels 171 --output json` 正确性 | ✅ agent_data 输出 pool+signatures，agent_analyze 输出五档组合，agent_review 用 combo JSON 测试通过 |
| 4 | `dump_level_pools.py` 可被 agent_data 直接调用 | ✅ agent_data 第15行 `from tools.dump_level_pools import build_level_pools, dump_all_pools` |

### ⚠️ WARN（3项）

| # | 检查项 | 严重度 | 说明 |
|---|--------|--------|------|
| 5 | `submit_batch_unity.py` 未集成 agent | 中 | 批跑后只调 dump_level_pools + post_batch_review，未调用任何 agent。三个 agent 是完全独立的手动 CLI 工具 |
| 3d | `tools/design_probes.py` 与 agent 独立 | 低 | design_probes.py 使用 bot400+phase2 迭代算法，agent_analyze._design_probes 使用 WR 匹配算法。两者逻辑不同且未互通 |
| 3e | `tools/preflight.py` / `tools/postcheck.py` 仍被需要 | 低 | agent 体系未覆盖 asset 完整性、probe_configs 完整性、Excel vs Asset 一致性检查。preflight/postcheck 仍需在提交前后运行 |

### ❌ FAIL（2项关键 + 1项次要重复）

| # | 检查项 | 严重度 | 说明 |
|---|--------|--------|------|
| **7** | **agent_data 安全约束是死代码** | 🔴 高 | `ALLOWED_WRITE_PREFIXES`、`FORBIDDEN_CMDS`、`_safe_check()` 已定义但**从未被调用**。`_safe_check()` 在 `refresh_pools()` 前应执行但被遗漏 |
| **6** | **缺少端到端流水线编排** | 🔴 高 | 当前链路: Unity batch → dump_level_pools → post_batch_review（无 agent 参与）。缺失: agent_analyze 自动选组合、agent_review 自动复核、自动应用组合到 asset |
| 3a | **judge_level.py 重复实现** | 🟡 中 | `judge_level.py` 仍保留完整 `find_best_combo()`（行148-288），与 `tools/find_best_combo.py` 和 `pool.find_best_monotonic` 三处重复。头部注释声明已迁移但未删除本地实现 |

### 错误自愈评估（#8）

| Agent | 重试 | 单关容错 | 问题 |
|-------|------|----------|------|
| agent_data | ✅ refresh_pools 重试1次（延迟3秒） | ✅ verify_signatures 逐关 catch | — |
| agent_analyze | ❌ 不重试 | ✅ main 循环 try/except 逐关捕获 | — |
| agent_review | ❌ 不重试 | ⚠️ review_level 内 catch asset_read_error | **无 try/except 包裹 combo JSON 解析**（格式错误直接 crash） |

## 修复优先级

1. **P0** — 激活 agent_data 的 `_safe_check`：在 `refresh_pools→dump_all_pools` 前调用
2. **P0** — 创建 `scripts/submit_orchestrator.py` 编排完整流水线：batch → agent_data → agent_analyze → agent_review → 用户确认
3. **P1** — `judge_level.py` 改用 `pool.find_best_monotonic`，删除本地 `find_best_combo()`
4. **P2** — `agent_review.py` 增加 combo JSON 解析 try/except + asset 读取重试
5. **P2** — `design_probes.py` 与 `agent_analyze._design_probes` 合并或明确职责边界
