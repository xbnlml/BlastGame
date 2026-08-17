# auto_loop 流水线修复：extract_json 多行 JSON + watchdog 监控（2026-08-08）

> 场景：auto_loop 全自动调优 85/119/120 启动即失败（3 关全 probe_design_failed_r1）。

## Bug：planner JSON 解析失败

**症状**：`planner: could not parse JSON output` → fallback design_probes 写了探针但重跑 planner 仍解析失败 → 3 关全 `probe_design_failed_r1` → auto_loop 立即停止。

**根因**：`scripts/auto_loop.py` 的 `extract_json()` 只支持**单行 JSON**（逐行找 `{` 开头且整行可 parse）。但 `tools/planner.py --output json` 输出：
- `json.dumps(results, indent=2)` → **多行格式化 JSON**
- analyze_level() 内部 print 的 debug 文本（"① 当前最优..."）混在 stdout 前面

→ 单行策略找不到完整 JSON，整个 stdout 又混噪声 → 返回 None。

**修复**（extract_json 加 Strategy 2 brace-span）：
```python
start = stdout.find('{')
end = stdout.rfind('}')
if start >= 0 and end > start:
    try:
        return json.loads(stdout[start:end + 1])
    except json.JSONDecodeError:
        pass
```
即：取第一个 `{` 到最后一个 `}` 之间的子串再 parse（支持多行 JSON + 前后噪声）。顺序：单行最后块 → brace-span → 整块 → 单行第一块。

**验证**：真实 planner 输出测试通过（含 debug 噪声 + 多行 JSON）；单行 JSON 回归通过；纯噪声返回 None。

## 同类预防：任何子进程 JSON 输出对接

- 子进程输出 JSON 前，**内部 debug print 必须走 stderr 或日志**，JSON 模式只输出纯 JSON（planner.py L119 的 debug 在 `--output json` 分支外，但 analyze_level 内部有 print）
- 解析端 extract_json 必须支持多行（brace-span 兜底）

## watchdog 模式（用户离开时全自动保障）

用户要求"确保全自动没问题，6 轮跑满，我不在了出问题自己解决"→ 建 `scripts/auto_loop_watchdog.py`：

- 检查：① 最新 auto-log 文件 mtime 是否 30 分钟内更新（进程活跃）② Unity.exe 是否在跑（batch 期间）③ 日志尾部是否含 `FINAL SUMMARY`/`FAILED` ④ `_rounds.json` 是否达 6 轮上限
- 正常输出 `OK: auto_loop 活跃`，异常输出 `⚠` 报警
- **Windows GBK 坑**：`tasklist` 输出 GBK 编码，subprocess 必须 bytes 模式 + `.decode('gbk', errors='ignore')`，否则 UnicodeDecodeError 崩溃
- cron 调度：`cronjob create` + `schedule='every 30m'` + `repeat=-1`（注意默认 repeat=once，要显式设 -1 才循环）；`no_agent=true` + `script='auto_loop_watchdog.py'`（脚本必须放 `~/AppData/Local/hermes/scripts/`，不能绝对路径）

## 全自动模式确认点（跑 6 轮前自查）

- `MAX_ROUNDS = 6`（auto_loop.py L76），主循环 `for round_num in range(1, MAX_ROUNDS+1)`
- 合格 → 只标记"合格待确认入库"（**不落盘**）；满 6 轮 → 只标记"待用户确认改关卡"（**不自动 retire_level**）——2026-08-05 用户裁定
- Unity batch 失败检测：submit 输出含 'passed'/'FAIL' 关键词判断
- **改过 C# 代码后首跑 = 隐式编译验证**：Unity batch 启动后几秒内不退 = 编译通过；telemetry 新文件生成 = 在跑模拟
