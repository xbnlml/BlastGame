# 工具设计决定 Agent 上限（第四课映射 + P0/P1 落地，2026-08-10）

> 用户用"每日会话第四课：工具设计决定 Agent 上限"审视 BlastGame 工具链后要求优化。
> 本文件 = 第四课原则 × 工具链现状 + 已落地的三处修复。

## 一、第四课六原则（工具 = 行动边界）

1. **工具描述**：写清能/不能/何时用（防相似工具混淆）
2. **参数设计**：能枚举就枚举、时间/数量明确上限、别让一个参数担多义、缺关键参数不硬编
3. **返回值结构化**：状态字段驱动分支判断 + evidence 证据 + suggested_next_actions
4. **工具粒度**：太细跑断（连续调 5-6 次一步错全断）；太粗失控（黑盒不可调试）——围绕一个业务动作封装
5. **有副作用工具单独边界**：读/写分离、单独确认、单独审计
6. **错误恢复**：返回 error 时告诉 Agent 怎么恢复（缺参数就反问），不能只报错

## 二、对照检查发现的问题（按严重度）

| 严重度 | 问题 | 工具 | 违反原则 |
|---|---|---|---|
| P0 | **"✅ 同步完成"但实际没写入**（DB 漏写当成功）| reimport.py | 4/6 伪成功 |
| P1 | Unity 失败只有 exit code（1073741845），原因靠猜 | submit_batch_unity.py | 3/6 非结构化 |
| P1 | 可达性预检只打印不阻断 → 目标远超天花板仍白跑 6 轮 | design_probes.py | 3/6 |
| P2 | 池子空时返回"无数据"无恢复引导 | judge_level.py | 6 |
| P2 | ratios/of 自由文本无校验 | probe_configs.json | 2 |

**✅ 做得好的**（对照课本）：judge_level 输出结构化（T1→T5+判定+操作）；--strategy 枚举；四元组 (sd/sc/ratios/of) 结构化契约；入库 reimport.py 统一 + 用户确认（读写分离）。

## 三、P0/P1 修复落地（已验证）

### P0: reimport.py DB 同步回读验证
- **根因**：`_sync_leveldb` 只查 `node 退出码 == 0`——write_level_db.mjs 输出"部分验证失败"时退出码仍 0 → DB 漏写当成功（L163 案例）
- **修复**：node 跑完后**回读 test.json**——确认 reimport entry 存在（sourceFileName 含 `reimport-YYYYMMDD-{lv}.json`）+ 逐档 dealConfig 匹配（normal dedup 后 ≥3 条），不匹配返回 False → 输出"⚠ DB 同步失败"

### P1a: design_probes 可达性预检默认阻断
- **根因**：verified 天花板 vs 目标 >15pp 只打印提示，仍返回探针 → 白跑 6 轮（L85/L119/L57 教训）
- **修复**：`design(lv, force_unreachable=False)` 默认阻断返回 None；CLI `--force` 绕过；**auto_loop fallback 同步修**——阻断时 probe_configs 无探针 → 不误加 ok_levels → 标记"待改关卡"不白跑

### P1b: submit_batch_unity 失败原因结构化
- **修复**：捕获 `Fatal Error!`/`another Unity instance` → `fatal_reason`（unity_conflict/unity_fatal_error/unity_timeout）→ 输出 `RESULT: {"status":"failed","reason":"unity_conflict","recovery":"..."}`（含恢复路径）+ 非零退出码

## 四、可用恢复路径速查

| reason | 含义 | 恢复 |
|---|---|---|
| unity_conflict | 另一个 Unity 实例占用项目 | 等它关闭或手动关闭后重试 |
| unity_fatal_error | Unity 致命错误 | 查看上方 [Unity] 输出定位 |
| unity_timeout | 超时被杀 | 检查关卡数量/局数是否过大 |
| db_sync_missing | reimport 后 DB 无 entry | 手动 `node tools/leveldb_sync/write_level_db.mjs` |

## 五、教训

- **"✅ 成功"必须有回读验证**——外部进程（node/Unity）退出码 0 不代表副作用生效
- **阻断比提示有效**——预检发现注定失败时默认阻断，比打印警告让流程继续跑省钱（6 轮 ≈ 2 小时白跑）
- **Agent 消费的是返回值不是日志**——失败原因 + 恢复路径必须出现在返回值里
