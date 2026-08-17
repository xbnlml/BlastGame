# 全自动调优工作流全面审查 — 2026-07-31（P0 已全修）

## P0 — 已修复 ✅

| # | 问题 | 修复 |
|---|------|------|
| 1 | Warden 未串联 | auto_loop Phase 3 前调用 `warden.py`，返回非 0 则 blocked |
| 2 | 轮次双增 | `judge_with_rounds()` 管理轮次，auto_loop 只读 `status['round']` |
| 3 | 规则硬编码 | `judge_level._load_rules()` 从 `project-state/rules.json` 动态加载 |
| 4 | "接近"被丢弃 | auto_loop 加 `status['result'] in ('合格', '接近')` |
| 5 | Curator 无代码 | `tools/curator.py` 创建，auto_loop 末尾调用，读日志→检测模式→更新 memory |

## P1 — 待优化

| # | 问题 | 建议 |
|---|------|------|
| 6 | submit_batch_unity 管道与 auto_loop 重复 | 去重或标记 dry-run |
| 7 | 池子被 3 脚本重复读取 | 加内存缓存层 |
| 8 | preflight/retire 未串联 | 改关卡后自动化清理 |
| 9 | agent memory 未注入 delegate_task | auto_loop 传 context 时附对应 memory |
| 10 | post_batch_review 未消费 | 结构化输出给 Curator |
| 11 | DESIGN_PROBES_QUIET 需手动设置 | auto_loop 内部自动设置 |
| 12 | 无 cron 调度 | 可手动触发，暂不急需 |
