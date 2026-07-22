# pipeline-progress-check.json Schema

> **⚠️ 2026-07-16 更新：推荐使用 `scripts/watchdog-checkpoint.py` 替代手动构造 JSON。**
> 该脚本读取 progress.json + 扫描 bot 目录 + 读取旧 checkpoint → 输出完整 JSON（含全部 7 个必填字段）。
> **单一终端命令即可完成写入，彻底消除 agent 手动构造 JSON 环节：**
> ```bash
> SKILL_DIR="/c/Users/Administrator/AppData/Local/hermes/skills/game-design/blastgame-auto-pipeline"
> CHK="C:/Users/Administrator/Documents/BlastGame/BuildLogs/pipeline-progress-check.json"
> python3 "$SKILL_DIR/scripts/watchdog-checkpoint.py" | python3 -c "
> import sys,json; d=json.load(sys.stdin)
> assert 'stuck_count' in d and 'last_stuck_alert' in d and 'last_check' in d
> json.dump(d, open(r'$CHK','w'), indent=2)
> print('CHECKPOINT WRITTEN: levels_done=%d stuck_count=%d stuck=%s' %
>       (d['levels_done'], d['stuck_count'], d['stuck']))
> " || echo 'WATCHDOG FAILED'
> ```
>
> **以下内容（validate-checkpoint.py 验证脚本、写前必查清单）保留为备选方案。** 但 13+ 次实例证明 agent 在手动构造 JSON 后经常跳过这些步骤。**首选方案是 `watchdog-checkpoint.py`。**

> **⚠️ 每次写入 checkpoint 前，必须依次执行以下两步：**
> 1. **构建你的 JSON 时，脑中过一遍「写前必查清单」（见下方），确保 stuck_count 和 last_stuck_alert 都在其中**
> 2. **先写到一个临时路径（如 `BuildLogs/_checkpoint.tmp.json`），然后运行验证脚本确认字段齐全，再覆盖正式路径：**
>    ```
>    python3 /c/Users/Administrator/AppData/Local/hermes/skills/game-design/blastgame-auto-pipeline/scripts/validate-checkpoint.py BuildLogs/_checkpoint.tmp.json && mv BuildLogs/_checkpoint.tmp.json BuildLogs/pipeline-progress-check.json
>    ```
>    验证脚本返回 0 才可覆盖，返回 1 必须先修正。
>
> **2026-07-15 18:07 证据链：** 即使在此 session 中 **已经加载了 checkpoint-schema.md 和 pipeline-watchdog.md 两份文档全部内容**，随后构造的 checkpoint JSON 仍然缺少 `stuck_count`、缺少 `last_stuck_alert`、且字段名错误（`last_progress_file_modification` 而非 `last_progress_update`）。**文档阅读无法解决此问题。写前运行 validate-checkpoint.py 验证脚本是唯一已被证明有效的方法。**
>
> **这是 2026-07-15 第 11+ 次修正后仍然发生的问题** — 无论文档写得多详细，agent 在 cron 模式下从 prompt 中的 "读取 levels_done" 出发构造 JSON，自然遗漏 prompt 中未提及的 stuck_count。**只有每次写前实际调用验证脚本才能打破这个模式。**

> 监控 cron job 每次运行时读取/写入的 checkpoint 文件。
> 用于跨会话对比 `levels_done` 变化、抑制重复告警、检测 bot 目录活动性。

## 路径

```
BuildLogs/pipeline-progress-check.json
```

## 最小模板（首次运行/快速生成时使用）

直接复制以下 JSON，填上当前值。确保 7 个必填字段一个都不少：

```json
{
  "last_check": "2026-07-13 22:59",
  "levels_done": 15,
  "levels_total": 50,
  "recent_bot_dirs": ["54_90_93-2026-07-13T21-05-59"],
  "latest_bot_timestamp": "2026-07-13 21:12",
  "last_progress_update": "2026-07-07 11:43",
  "stuck_count": 0,
  "last_stuck_alert": null
}
```

**⚠️ 首次写入时 `stuck_count = 0` 是必须的** — 不要省略此字段。下次检查时看门狗根据 `stuck_count` 决定是否投递。首次写入就缺了它，下次检查就永远按第一次卡住处理（抑制链初始化失败）。

**完整示例（2026-07-14 19:58 实际使用版本）：**
```json
{
  "last_check": "2026-07-14 19:58",
  "levels_done": 15,
  "levels_total": 50,
  "scope": "51-100",
  "latest_bot_dir": "80-80-2026-07-14T18-43-28",
  "last_bot_activity": "2026-07-14 18:45",
  "bot_active_30min": false,
  "recent_bot_dirs": ["80-80-2026-07-14T18-43-28 (T3 53.0%, T4 31.75%)", "80-80-2026-07-14T18-41-49", "L80-80-T3-2026-07-14T18-21-25", "L80-80-T2-2026-07-14T18-20-25"],
  "new_dirs_since_last_check": 4,
  "last_progress_update": "2026-07-14 18:45",
  "auto_batch_request": {"level": 80, "tiers": "3,4", "status": "unconsumed", "written": "18:34"},
  "stall_record": {"timestamp": "2026-07-14T19:44:06", "levels": ["80"], "tiers": "2,3"},
  "submit_batch_active": false,
  "submit_batch_level": "none",
  "unity_editor_running": false,
  "pipeline_phase": "stalled (waiting for Unity)",
  "levels_status": {"done": 15, "ggk": 44, "pending": 0, "optimized": 17},
  "stuck": true,
  "stuck_reason": "levels_done frozen at 15 since Jul 7 (7 days); Unity not running; submit_batch exited after producing L80 T3/T4 data (18:45); _stall.json written at 19:44"
}
```
此示例包含全部推荐的可选字段，是看门狗在既有数据又有 stall 的混合状态下的完整记录。`new_dirs_since_last_check=4` 明确说明自上次 cron 以来有新产出，即使当前静默。

**可选字段（推荐一并填入）**：`scope`, `bot_active_30`, `unity_running`, `stuck`, `stuck_reason`, `auto_batch_request_exists`, `auto_batch_request_levels` 等。详见下方完整 schema。

## Schema（完整）

```json
{
  "last_check": "2026-07-08 01:30",
  "levels_done": 15,
  "recent_bot_dirs": [
    "52-100-2026-07-08T01-22-00"
  ],
  "latest_bot_timestamp": "2026-07-08T01:22",
  "last_progress_update": "2026-07-07 11:43",
  "stuck_count": 0,
  "last_stuck_alert": null
}
```

| 字段 | 类型 | 要求 | 用途 |
|------|------|------|------|
| `last_check` | string | `YYYY-MM-DD HH:MM` 格式 | 本次检查时间 |
| `levels_done` | int | ≥ 0 | 上次读取的 `pipeline-progress.json` 的 `levels_done` 值 |
| `levels_total` | int | **可选** | `pipeline-progress.json` 的 `levels_total` 值（关卡总数），用于报告进度百分比 |
| `scope` | string | **可选** | 当前管道的关卡范围描述，如 `"51-100"` |
| `recent_bot_dirs` | string[] | 可空，有活动时应有 1+ 条 | 最近 30 分钟内出现的新 bot 目录完整路径列表 |
| `latest_bot_timestamp` | string | ISO 格式或 `HH:MM` | 最新 bot 目录的时间戳 |
| `last_progress_update` | string | ISO 格式 | `pipeline-progress.json` 文件的 mtime |
| `stuck_count` | int | **必需，初始 0** | 连续卡住检测计数。用于看门狗告警抑制：0=未卡住, 1=首次, 2=第二次, 3+=[SILENT] |
| `last_stuck_alert` | string\|null | ISO 格式或 null | 上次投递卡住告警的时间。null=从未投递过 |
| `done_array_count` | int | **可选**，推荐 | `pipeline-progress.json` 中 `done` 数组的实际长度。用于自检：与 `levels_done` 不一致说明 JSON 数据受损或手动修改过 |
| `stuck` | bool | **可选** | 本次检查的卡住判定结果。方便快速读取，不用重新计算 |
| `stuck_reason` | string | **可选** | 卡住原因的文字描述，供人工审查。每次检查都应更新为最新原因 |
| `new_dirs_since_last_check` | int | **可选** | 上次检查以来新增的 bot 目录数量。用于快速判断管道活动趋势 |
| `total_bot_dirs` | int | **可选** | bot 目录总数。⚠️ **写入时是快照值，验证时要用 `>=` 而非 `==`**：管道可能在验证窗口内创建新目录，精确匹配会在活管道的验证中持续失败 |
| `auto_batch_request_exists` | bool | **可选** | checkpoint 写入时 `auto-batch-request.json` 是否存在于文件系统中 |
| `auto_batch_request_levels` | string | **可选** | request.json 中的关卡列表描述，如 `"52,55,56,57,59,69,74,87,96 (verify-round3, T1-T5 all DONE)"` |
| `pending_levels` | string[] | **可选** | 从 `pipeline-progress.json` 读取的待处理关卡列表（通常来自 `levels.pending` 数组）。看门狗写入此字段供历史对比，追踪 pipeline 是否正确从 pending 推进到 done |
| `auto_batch_request_mtime` | string | **可选** | request.json 文件的 mtime ISO 时间戳 |
| `stall_record` | object | **可选** | `_stall.json` 的快照（含 `timestamp`、`levels`、`tiers`）。看门狗写入此字段后在下次检查时可判断是否出现了新的 stall 记录，用于 cron 间比对。示例：`{"timestamp":"2026-07-14T19:44:06","levels":["80"],"tiers":"2,3"}` |
| `submit_batch_active` | bool | **可选** | 当前是否有 `submit_batch.py` 进程在运行。用 `ps -W | grep submit_batch` 检测 |
| `submit_batch_level` | string | **可选** | submit_batch 当前处理的关卡（如 `"80"`、`"none"`）。结合 `submit_batch_active` 判断驱动链是否活跃 |
| `pipeline_phase` | string | **可选** | 管道当前阶段的文字描述（如 `"dead"`、`"stalled (waiting for Unity)"`、`"optimizer running"`、`"bot batch active"`）。**认可值 `"dead"`**：Unity 进程不存在且 `auto-batch-request.json` 存在但陈旧（未消费）。比 `"stalled"` 更明确——dead 需要先重启 Unity 才能恢复。详见 SKILL.md「管道阶段演进」 |
| `levels_status` | object | **可选** | pipeline-progress.json 中各状态分类的计数快照。结构：`{done: int, ggk: int, pending: int, optimized: int}`。看门狗一次读取后固化，便于后续对比而不必每次重新解析 progress JSON |
| `multi_tier_opt_latest` | string | **可选** | `multi-tier-opt/` 目录下最新结果的时间戳，用于判断优化器是否在消费新数据。**⚠️ 必须递归扫描子目录 ctime，不能只取顶层目录 ctime**——顶层目录创建后不再更新 ctime，看门狗在 2026-07-12 发现 11 个子目录持续写入但父目录 ctime 显示 13.6h 前的假阴性。详见 `pipeline-watchdog.md §13` |
| `latest_optimizer_subdir` | string | **可选** | 优化器当前处理的关子目录描述，如 `"98-2026-07-12T08-40-36 (L98, phase0_prior at 08:43)"`。用于快速在报告中展示优化器正在处理的关卡和阶段 |
| `optimizer_active_in_30min` | bool | **可选** | 最近 30 分钟内优化器是否有写入活动。看门狗用此直接判断优化器活性，避免每次重新计算 ctime 差值 |
| `optimizer_current_batch` | string | **可选** | 优化器当前批次的名称，如 `"51_54_63_65_68_74_77_82_86_89-90_92-94_98"`。用于快速区分跨批次的优化活动 |
| `optimizer_batch_progress` | string | **可选** | 批次内各关完成状态的可读字符串，如 `"51✅ 54✅ 63✅ 65✅ 68✅ 74✅ 77✅ ... 98🔄(in progress)"`。便于一眼看清批次内部进度。⚠️ 当所有关都变为 `✅` 时（如 `"51✅ 54✅ ... 98✅ (just finished)"`），结合无运行中进程，看门狗应识别为 **Optimizer Post-Batch Stall**（见 `pipeline-watchdog.md §14`），而非优化器仍在工作 |

> **⚠️ 常见错误：忘记 `stuck_count`。** Cron watchdog 实现中容易忽略此字段（如 2026-07-08 04:51 的检查就漏写了）。缺失此字段会导致下次检查无法识别上一轮是否已告警，从而绕过告警抑制规则，每次 cron 都投递完整报告。**修复方法：** 发现缺失时，看门狗应设 `stuck_count = 0` 初始化，并返回中说明首次进入抑制循环。
>
> **⚠️ 常见错误：错误字段名（自洽但不符合 schema）。** 除了漏字段，agent 还常使用与 schema 字段名不同的名称，导致未来读取时无法正确映射。已观察到的错误变体（及正确名称→）：
>   - ❌ `recent_bot_dirs_30min` → ✅ `recent_bot_dirs`（2026-07-17 实例：checkpoint 文件使用此错误名，`recent_bot_dirs` 不存在）
>   - ❌ `latest_batch_timestamp` → ✅ `latest_bot_timestamp`（同实例：`latest_bot_timestamp` 不存在）
>   - ❌ `last_progress_file_update` / `last_progress_file_modification` → ✅ `last_progress_update`（2026-07-15 实例）
>   - ❌ `check_time` → ✅ `last_check`（早期实例）
>
> **根因：** agent 从 cron prompt（"读取 levels_done"）出发，自创看似合理但偏离 schema 的字段名。更严重的是，文件系统上持久化的 checkpoint 使用这些错误名称，后续 agent 读取该文件作为"之前格式"的模板，会继续使用错误字段名，形成**自我强化的错误循环**——每个新检查看到的都是错误的字段名，然后复制它们。
>
> **修复方法：** 写入前对照本文档的完整 schema 表逐字段名称校验。**不要信任磁盘上已有的 checkpoint 文件的字段名**——它可能也是由前面犯错的 agent 写出的。始终以本文档的 schema 表为权威来源。使用 `validate-checkpoint.py` 验证脚本会捕获字段名错误（返回非 0 退出码）。
>
> **2026-07-15 18:07 再次确认（本轮 session）：即使已经在同一个 cron session 中加载了 checkpoint-schema.md 和 pipeline-watchdog.md 全部内容，最终写入的 checkpoint 仍然缺少 `stuck_count` 和 `last_stuck_alert`，且字段名错误。** 写入的 JSON 含 `new_dirs_since_last_check`, `total_bot_dirs`, `last_checkpoint_levels_done`, `last_checkpoint_time`, `previous_status` 等共 13 个字段——但缺了抑制所依赖的 stuck_count 和 last_stuck_alert，且用了 `last_progress_file_modification` 而非 `last_progress_update`。**根因不变：cron prompt 只要求读 levels_done，agent 构造 JSON 时自然只含 prompt-visible 字段。** 解决方案不是「读文档更仔细」（已失败 12+ 次），而是「先写 tmp 文件 → 运行 validate-checkpoint.py 验证通过后再覆盖」。

> **⚠️ Cron 模式下 execute_code 被禁止。** Hermes cron job 不允许运行 `execute_code`（任意本地 Python 可能含子进程调用，cron 无用户批准机制）。以下伪码仅作概念参考。**实际看门狗实现必须仅用 `write_file` + `terminal` 两个工具：**
> - `terminal` 用于读取数据（`cat`, `find`, `stat`, `date`, `grep`）和计算时间差
> - `write_file` 用于写入 JSON checkpoint（agent 在思维中构建 JSON，用 write_file 一次性写出）
>
> **Python heredoc（`python3 << 'EOF' ... EOF`）在 terminal 中是允许的**，仅用于临时验证脚本（无 JSON I/O、无子进程调用、无外部副作用）。实际使用（2026-07-11 验证）确认可正常通过 cron 安全策略。但注意：
> - ❌ `python3 -c "import json; ..."` 内联 —— 被 terminal 工具的安全检查拦截（shell 字符串审批无法验证内联 Python 的安全性）
> - ✅ `python3 << 'PYEOF' ... PYEOF`（heredoc）—— 通过安全检查，因为终端工具能清晰识别这是向 python3 stdin 输送文本
> - ❌ `execute_code` —— 始终被 cron 安全策略禁止
>
> **正确做法：** agent 用 `read_file` 读 `pipeline-progress.json`，用 `terminal` 读 mtime 和 bot 目录列表，在思维中完成比较逻辑，用 `write_file` 写出构建好的 checkpoint JSON。仅在需要临时验证结果时才用 heredoc Python 做简单的格式/一致性检查。

## 检查逻辑伪码

```python
# 读取
prev = read checkpoint  # may be None
curr = json.load(open('BuildLogs/pipeline-progress.json'))

# 交叉验证 levels_done vs done 数组长度
assert curr['levels_done'] == len(curr['levels']['done']), \
    f"levels_done {curr['levels_done']} != done array len {len(curr['levels']['done'])}"

# 精确时间窗检查（-newermt 而非 -mmin -30，避免滑窗效应）
last_check_time = prev.get('last_check', None) if prev else None
if last_check_time:
    # 将 "2026-07-08 13:26" 转为 ISO 格式
    from datetime import datetime
    anchor = datetime.strptime(last_check_time, '%Y-%m-%d %H:%M').strftime('%Y-%m-%d %H:%M:%S')
    cmd = f'find telemetry/bot/ -newermt "{anchor}" -type d 2>/dev/null'
else:
    # 无前次记录时用常规 -mmin -30
    cmd = 'find telemetry/bot/ -mmin -30 -type d 2>/dev/null'
bots = subprocess.check_output(cmd, shell=True).decode().strip().splitlines()

# 也检查当天活动（Burst 检测）
today_cmd = f'find telemetry/bot/ -newermt "{date.today().isoformat()}" -type d 2>/dev/null'
today_bots = subprocess.check_output(today_cmd, shell=True).decode().strip().splitlines()

# 交叉验证记录
done_array_actual = len(curr['levels']['done'])
```

if curr.levels_done > prev.levels_done OR bots changed:
    # 有推进
    prev.stuck_count = 0
    输出正常/恢复报告
elif prev.stuck_count == 0:
    prev.stuck_count = 1
    输出首次卡住告警（🔴 完整报告）
elif prev.stuck_count == 1:
    prev.stuck_count = 2
    输出第二次卡住告警（⚠️ 简要升级报告）
else:
    prev.stuck_count += 1
    [SILENT]  # 抑制重复投递

prev.last_check = now
prev.recent_bot_dirs = bots
prev.latest_bot_timestamp = bots[0] or "无"
prev.last_progress_update = curr_file_mtime
write checkpoint
```

## ⚠️ 写前必查清单（每次写入 checkpoint 前逐项核对）

> **为什么需要这个清单？** 无论文档写得多详细，看门狗 cron job 仍然反复写出缺少 `stuck_count` 的 checkpoint（实例：2026-07-08, 2026-07-09, 2026-07-10, 2026-07-14, 2026-07-15）。根因是 cron prompt 只要求读 `levels_done`，agent 自然只构造 JSON 中的 prompt-visible 字段。**必须靠写前自检中断这个模式。**

**写入 `pipeline-progress-check.json` 前，逐条检查以下 6 项：**

```
□ ① 是否包含 stuck_count（int，必须已有值，初始 0）？
□ ② 是否包含 last_stuck_alert（string|null，首次写 null）？
□ ③ 字段名是否正确（last_check 非 check_time，latest_bot_timestamp 非 latest_bot）？
□ ④ 字段数量≥7（last_check, levels_done, recent_bot_dirs, latest_bot_timestamp,
     last_progress_update, stuck_count, last_stuck_alert 至少这 7 个）
□ ⑤ stuck_count 的值是否与状态一致？（有进展=0，无变化但活动=不递增，首次卡住=1，等等）
□ ⑥ 是否已优先考虑使用 `scripts/watchdog-checkpoint.py` 替代手动构造 JSON？
    命令: python3 scripts/watchdog-checkpoint.py > BuildLogs/pipeline-progress-check.json
    (如使用手动构造，是否调用了 validate-checkpoint.py 验证脚本并收到返回码 0？)
    命令: python3 scripts/validate-checkpoint.py BuildLogs/_checkpoint.tmp.json && mv BuildLogs/_checkpoint.tmp.json BuildLogs/pipeline-progress-check.json
```

**如果以上任何一项为 ❌，修正后再写入。** 不要直接运行 `write_file`。

**最小可接受模板（写入前脑中校验）：**

```json
{
  "last_check": "2026-07-14 14:21",
  "levels_done": 15,
  "recent_bot_dirs": ["93-93-2026-07-14T13-34-20"],
  "latest_bot_timestamp": "2026-07-14T13:34",
  "last_progress_update": "2026-07-07 11:43",
  "stuck_count": 0,
  "last_stuck_alert": null
}
```

对比你的 JSON，是否所有字段都存在且类型正确？如果缺了任何一个，回到清单重新检查。

---

## 首次运行

`pipeline-progress-check.json` 不存在时，无法做 delta 比较。
此时按 **stuck_count = 0** 处理（输出完整报告，不做卡住判定）。
写入首次 checkpoint 供下次对比。
