# Pipeline 看门狗 — 管道卡住诊断与告警

> **⚠️ 2026-07-16 重要更新：`scripts/watchdog-checkpoint.py` 替代手动 JSON 构造。**
> 该脚本自动化完成 checkpoint 的完整构造：读取 progress.json → 扫描 bot 目录 → 读取旧 checkpoint → 计算 delta → 输出完整 JSON（含 stuck_count + last_stuck_alert 等全部 7 个必填字段）。
> **这是唯一被证明能消除 stuck_count 遗漏的方案。** 15+ 次实例（2026-07-07 ~ 07-16）表明 agent 手动构造的 JSON 必然遗漏 prompt 中未提及的字段，即使文档已加载。**不要再手动写 checkpoint JSON。**
>
> **用法（写 checkpoint 的单一终端命令）：**
> ```bash
> SKILL_DIR="/c/Users/Administrator/AppData/Local/hermes/skills/game-design/blastgame-auto-pipeline"
> CHK="C:/Users/Administrator/Documents/BlastGame/BuildLogs/pipeline-progress-check.json"
> python3 "$SKILL_DIR/scripts/watchdog-checkpoint.py" | python3 -c "
> import sys,json; d=json.load(sys.stdin)
> assert 'stuck_count' in d and 'last_stuck_alert' in d
> json.dump(d, open(r'$CHK','w'), indent=2)
> print('CHECKPOINT WRITTEN: levels_done=%d stuck_count=%d stuck=%s' %
>       (d['levels_done'], d['stuck_count'], d['stuck']))
> " || echo 'WATCHDOG FAILED'
> ```
>
> **旧方案（validate-checkpoint.py + 手动构造 JSON）保留为备选**，但 15+ 次失败记录证明 agent 在手动构造后经常跳过验证。**优先使用 watchdog-checkpoint.py。**

> **⚠️ 每次写入 checkpoint 前必查：`stuck_count` 字段是否存在。** 如果 `pipeline-progress-check.json` 缺少 `stuck_count`（或文件是新建的），设 `stuck_count = 0` 再写入。
> 这是 checkpoint schema 的硬要求，也是告警抑制的根基。2026-07-08 到 2026-07-15 共 11+ 次 cron 检查仍漏写此字段，导致每次投递完整报告。
> 详见 `references/checkpoint-schema.md`「常见错误: 忘记 stuck_count」。
>
> **2026-07-15 18:07 实例证明：即使在同一个 cron session 内刚刚加载了 checkpoint-schema.md 和 pipeline-watchdog.md 两份文档，代理仍然写出了缺少 `stuck_count`、缺少 `last_stuck_alert`、且字段名错误（`last_progress_file_modification` 而非 `last_progress_update`）的 checkpoint。** root cause 不变：cron prompt 只要求读 levels_done，代理构造 JSON 时自然只含 prompt-visible 字段。**解决方案不是「更仔细地读文档」——已经证明 12+ 次警告无效。唯一有效的方法是「先写 tmp 文件 → 运行 validate-checkpoint.py 验证通过 → 再用 mv 覆盖正式路径」。** 验证脚本返回 0 前不要调用 write_file。
>
> **强制防护：** `scripts/validate-checkpoint.py` 在写入前验证必填 7 字段。**先写 tmp 文件 → 运行验证 → 返回 0 才覆盖正式路径。** 详见 `references/checkpoint-schema.md` 顶部使用说明。

> 自动检测调优管道是否卡住，卡住时通过 cron job deliver 通知用户。
> 本文件记录所有诊断信号、检查步骤和状态判定规则。

### 写 checkpoint 前请确认：「我的 JSON 包含 `stuck_count` 字段吗？」

```json
{
  "last_check": "2026-07-13 21:53+08",               ← 当前检查时间（字段名遵循 checkpoint-schema.md）⚠ 不是 check_time
  "levels_done": 15,                                 ← pipeline-progress.json 的 levels_done
  "levels_total": 50,                                ← 可选，推荐 — 关卡总数，用于进度百分比
  "scope": "51-100",                                 ← 可选，推荐 — 管道范围
  "recent_bot_dirs": ["54_90_93-2026-07-13T21-05-59"], ← 最近 bot 目录列表（必填，至少保留一条）
  "latest_bot_timestamp": "2026-07-13 21:12",        ← 最新 bot 目录的时间戳
  "last_progress_update": "2026-07-07 11:43",        ← pipeline-progress.json 的 mtime
  "stuck_count": 1,                                  ← ← ← 必须存在！告警抑制的根基（初始 0）
  "last_stuck_alert": "2026-07-13 21:53",            ← 上次投递卡住告警时间（首次写 null）
  "bot_active_30": false,                            ← 可选：最近 30 分钟有新 bot 目录？
  "unity_running": false,                            ← 可选：Unity 进程是否运行？
  "stuck": true,                                     ← 可选：本次检查的卡住判定
  "stuck_reason": "levels_done=15 frozen; Unity exited after 21:12 batch; stale request.json (TryDelete failed)"  ← 可选
}
```

> **2026-07-13 再次陷阱确认：** 即使 doc 已有大量 stuck_count 警告，本轮 cron watchdong 仍然写出了 `missing stuck_count` 的 checkpoint（用了 `check_time` 非 `last_check`，缺 `stuck_count`/`recent_bot_dirs`/`last_stuck_alert` 等字段）。根因：cron 实现从任务描述（"读取 levels_done"）出发，自然忽略尖括号外的字段。**每次写 checkpoint 前，先在脑中扫一遍此 JSON 示例，确认字段齐全。**
>
> **参数字段名必须遵循 `checkpoint-schema.md` 的规范——`last_check`（非 `check_time`）、`stuck_count`、`recent_bot_dirs`、`last_stuck_alert` 为必填。** 注意：本文件顶部的 JSON 示例也已修正为使用 `last_check` 而非错误的 `check_time`，两文件保持一致的命名约定。可选字段（`bot_active_30`/`unity_running`/`stuck`/`stuck_reason`/`levels_total`/`scope`）推荐填写以便快速判读。
>
> **BuildLogs 目录中没有 `pipeline-progress-check.json` 文件也等价于没有 `stuck_count` 字段。** 当文件本身不存在时，代理在首次检查中会创建包含部分字段的新文件，此时大概率漏写 `stuck_count`。建议首次写入时直接用以下最小模板确保字段齐全。

## 诊断信号总览

管道"卡住"不是单一症状，以下信号各有权重：

| 信号 | 优先级 | 含义 |
|------|--------|------|
| `levels_done` 连续两次无变化 | 🔴 高 | 进度未推进（需配合其他信号确认）|
| 同关卡反复跑（bot 目录 level 前缀不变） | 🔴 高 | 管道在同一个关卡空转（agent 未推进到下一关）|
| 最近 30 分钟无新 bot 目录 | 🔴 高 | agent 可能卡在了某个步骤上 |
| **新 bot 目录存在但为空（无 T1-T5 子目录）** | 🟢 低 | Unity 刚创建批次根目录，尚未开始写入 tier 数据。这是 **准备信号**，不是卡住 |
| `auto-batch-request.json` 不存在 | 🔴 高 | agent 未提交新关或提交后已消费 |
| `auto-batch-request.json` 存在 + Unity 日志显示正在跑旧批次 | 🟡 中 | **批次排队中** — Unity 正在处理一个长批次（如 49 关），新请求等待当前批次完成后才消费。不是卡住，但需确认旧批次仍有活动 |
| **`auto-batch-last-export.txt` 指向不存在的 bot 目录（export-before-creation）** | 🟡 中 | **导出引用悬空** — `auto-batch-last-export.txt` 的 mtime 新（如 <30min）但指向的 bot 目录路径在 `ls` 中不存在。说明 pipeline export 操作已完成（写入导出索引），但 Unity 尚未实际创建 bot 目录。可能原因：(a) Unity 消费但刚创建批次根目录尚未写入 tier CSV；(b) 导出脚本在 Unity 消费 request 前就记录了路径（过早导出）；(c) submit_batch 的 RequestQueue 阶段完成后 Unity 未响应。检测：`cat auto-batch-last-export.txt` → 取 basename → `ls -la telemetry/bot/<basename>/`。目录不存在 + export mtime 新鲜 → 🟡 需检查 Unity 是否在响应 |
| **`auto-batch-last-export.txt` 指向不存在的 bot 目录 + 时间戳晚于实际批次完成时间（phantom-path-after-completion）** | 🟡 中 | **导出虚路径** — `auto-batch-last-export.txt` 记录了一个带有 *未来* 时间戳的路径（如 `...T17-13-21`），而实际的批次目录时间戳更早（如 `...T16-16-57`），且该路径在文件系统中不存在。与 export-before-creation 的区别：不是导出过早，而是 export 在批次完成后记录了一个 **预测/意向路径** 而非实际的出口目录。说明 export 步骤可能提前构造了路径名然后未能正确写入。检测：比对 `auto-batch-last-export.txt` 中的时间戳与最新 bot 目录的时间戳——如果 export 路径的 timestamp 比任何现有目录都新（晚于最新目录），则 phantom path 确认。`{"auto-batch-request.json` 存在 + 同一 level 反复出现新 bot 目录 + levels_done 冻结** | 🔴 高 | **TryDelete 失败循环** — request.json 从未被删除，Bot 反复执行同一请求。Unity PollForRequest 每次轮询都看到同一个 request.json（mtime 不变），重新执行→新目录→TryDelete 再次失败→循环。结果目录无限增长但永不晋级。与 stale request（§4）的区别：stale 是 mtime 早于最新 bot 目录且无新活动；循环中 bot 目录不断增长。检测：记录 request content hash 跨次比较；计数同一 level 前缀 bot 目录增长趋势 |
| Unity 进程存在但长期无活动 | 🟡 中 | 需确认 Unity 是在等待还是在排查 |
| **Unity 内存连续下降** | 🟡 中 | Unity.exe 的 WorkingSet 在两次检查间明显下降（如 3.2GB→1.6GB），即使进程仍在，内存收缩说明引擎可能已完成处理进入空闲/挂起。配合无新 bot 目录 + 无新日志输出综合判定 |
| **Unity 退出码为 3 或 4（编译错误）** | 🔴 高 | `unity-launch-*.log` 中出现 `ExitCode: 3` 或 `ExitCode: 4`，伴随 `CS0117` 行。**Unity 无法进入 Play Mode，request 永远不会被消费。** 根因是代码编译错误，非运行时问题。不同于崩溃——重启无法解决，必须修改 .cs 文件补齐缺失字段 |
| `pipeline-progress.json` 修改时间远早于最后批次 | 🟡 中 | 进度文件未同步 → 需综合判断 |
| **`levels_done` 14h 不变 + 持续有新 bot 目录 + Unity 日志活跃** | 🟡 中 | **数据收集模式** — Unity 正在跑一个大批次（如 49 关全部），`levels_done` 只反映已晋级关卡数，不反映批次活动。以 Unity 日志 mtime 为实时信号 |
| **stuck_count≥3 后突然出现新 bot 目录 + Unity 刚启动 + levels_done 仍冻结** | 🟡 中→🔴 高 | **Post-Stuck Retest Flurry（§18）** — 管道机械活性已恢复（Unity 重启成功），但只产出 ggk 关的 retest 目录，无任何关晋升到 done。`levels_done` 持续冻结（可能 9+ 天）。stuck_count 应归零但 stuck_reason 需注明"levels_done 未随活性恢复" |
| **同一关卡隔短时间（<1h）出现全 5 档 retest（Full T1-T5 Retest）** | 🟡 中→高 | **重复全量验证** — 不同于 T 子集验证轮次（只跑 2-3 个 tier），全 5 档 retest 说明 optimizer 在频繁生成全量新配置并要求 Bot 完全验证。auto-batch-result.json 通常不存在。管道在已有关卡上深度空转，pending 关从不触及 |
| **`auto-batch-result.json` 完全不存在（非 stale，是 never existed）** | 🔴 高 | **评估链从未初始化** — 自本次 Unity 会话启动以来，AutoBatchTrigger 的 WriteResult → TryDelete 循环从未成功完成过。即使 bot 目录有完整数据，result.json 缺失意味着 ingestion 链的起点就断了。详见 §16 实例 B |
| Unity.ILPP.Runner.exe 存在 | 🟢 低 | IL2CPP 正在构建 — 这是 _活跃_ 信号 |
| **`pipeline-status.txt` 内容长期冻结** | 🟡 中 | 即使 `levels_done` 未变，`pipeline-status.txt` 内记录的已完成/剩余关卡数若长时间不变（如持续显示 "8/27 completed" 超过数小时），说明批次完成后的 ingestion 链已断裂。与 `auto-batch-request.json` 不存在配合使用 |
| **`unity_editor_running = false` + 有新 `-batch-range` bot 目录（含 CSV 数据）** | 🟢 低 | **Batch-Mode 正常活性** — Unity Editor 未运行，但 `submit_batch_unity.py` 正在用 headless Unity 实例产出测试数据。这是预期的 batch-mode 行为，不是卡住。看门狗应记录 `batchmode_active = true` 而非判 `stuck = true`（详见 §3 关键区分）|

---

## 详细检查步骤

### 1. 基础数据 — pipeline-progress.json（含 mtime 信号）

**路径**: `BuildLogs/pipeline-progress.json`

```json
{
  "scope": "51-100",
  "levels_total": 50,
  "levels_done": 9,
  "levels": { ... }
}
```

**注意**: `levels_done` 可能 **滞后于实际批次活动**。如上次会话所示，该文件最后修改于 7月4日，但第 55 关的批次于 7月6 日仍成功运行。说明驱动脚本可能不再更新该 JSON，但 Unity Editor 仍在处理请求。

**📌 关键信号：`pipeline-progress.json` 的 mtime 是"最后 ingestion 时间"**，比 `levels_done` 数值更可靠。即使 `levels_done` 没变，mtime 更新了也说明有脚本在写进度——这是活性信号。反之，如果 mtime 远早于最新 bot 目录时间（如 30h vs 3h），说明 ingestion 链已断裂，是管道的根本问题。

**检查命令**:
```bash
# 读取 levels_done
cat /c/Users/Administrator/Documents/BlastGame/BuildLogs/pipeline-progress.json | grep levels_done
# 查看文件修改时间（= 最后 ingestion 时间）
stat -c '%y' /c/Users/Administrator/Documents/BlastGame/BuildLogs/pipeline-progress.json
```

### 2. 批跑输出目录 — telemetry/bot/

**路径**: `telemetry/bot/`

目录命名格式: `{level}-{level}-{timestamp}`, `{level1_level2}-{timestamp}`, 或 **批量格式** `L{level_list}-T{N}-{timestamp}-batch-range`

> **批量格式（2026-07-08 新观察）**: `L51_55_57_61-65_70_76-78_80-81_83-85_87-88_91_94-95_97_99-100-T5-2026-07-08T15-03-05.037-batch-range`
> 特征：L 前缀 + 逗号/范围混合列表 + T{1-5} 标记 tier + 时间戳 + `-batch-range` 后缀。这是全自动调优管道提交大批次（26+ 关 × 5 档）时的新命名约定。
>
> **⚠️ 验证轮次：T 子集模式（2026-07-15 新观察）** — 同一批次的 `batch-range` 目录可能只包含 **T 的子集**（如只有 T1/T3/T5，没有 T2/T4）。这是**验证轮次**的特征——管道跳过中间档位以节省时间（每个 tier 约 22-25 分钟，跳过 2 个 tier 省 40-50 分钟）。
> ```
> L53_56-57_59-T1-2026-07-15T10-15-04.190-batch-range/  ← 有
> L53_56-57_59-T3-2026-07-15T10-19-03.550-batch-range/  ← 有 (T2 跳过)
> L53_56-57_59-T5-2026-07-15T10-22-50.903-batch-range/  ← 有 (T4 跳过)
> ```
> 实例（2026-07-15）：`L53_56-57_59` 批次只有 T1/T3/T5 三个目录，而同一会话中的 `L54-54` 批次是全 5 档完整集。这暗示：对**改关卡 verification**，管道可能只跑少量档位做快速验证；对**新关 tuning**，才跑全 5 档。
> **看门狗影响：** 当检测到 T 子集模式时，(a) 不要误判为"批次未完成"（T2/T4 是跳过不是待产生），(b) 这是验证轮次而非全轮 tuning 的信号——验证轮次完成后管道可能不会自动推进到下一关，因为这只是对已有结果的再确认。
> **`verify-round{N}` 标签**: `auto-batch-request.json` 中的 tag 字段。如 `"tag": "verify-round3"` 表示第三轮验证批次。与 `auto-round{N}` 不同——verify-round 是对已标记改关卡的重测，auto-round 是正常调优轮次。Bot 目录名不含此标签，需从 request.json 追溯。
> 一个完整批次会生成 5 个这样的目录（T1–T5 各一个），每个约 22-25 分钟间隔。
> **扫描注意**：`find`/`ls` 直接扫根目录即可，不需要匹配前缀模式。
>
> **⚠️ 批量格式目录的内部结构（与旧格式不同）：** 旧格式目录（如 `55-55-2026-07-04T23-43-43`）内部有 `campaign-attempts-55.csv` 和 `campaign-summary-55.csv` 等按关命名单个 CSV。**批量格式目录（带 `-batch-range` 后缀）的内部结构不同：**
> ```
> L58_71_75-T5-2026-07-10T11-12-51.466-batch-range/
> ├── campaign-attempts-L58_71_75-T5.csv   ← 单文件含全部 3 关数据
> ├── campaign-summary-L58_71_75-T5.csv    ← 单文件含全部 3 关汇总
> └── replays/                              ← 回放目录（可能为空）
> ```
> 其中 `campaign-summary-*.csv` 有 `LevelGroup` 列区分各关（如 `test,58,...`、`test,71,...`、`test,75,...`），通过 `level` 列按行抽取对应关卡数据。脚本读取时应按 `level` 列过滤，不能假设文件名对应单关。

> **扫描注意**：`find`/`ls` 直接扫根目录即可，不需要匹配前缀模式。

**检查命令**:
```bash
# 列出最近 bot 目录（按时间排序）
ls -lt /c/Users/Administrator/Documents/BlastGame/telemetry/bot/ | head -5
# 查看最新目录的修改时间
stat -c '%y' "/c/Users/Administrator/Documents/BlastGame/telemetry/bot/$(ls -t /c/Users/Administrator/Documents/BlastGame/telemetry/bot/ | head -1)"
```

**判定**: 最近 30 分钟内有新目录 → 管道在正常运行。否则标记为"无活动"。

**精确时间窗检查（`find -newermt` 替代 `-mmin`）**：

当看门狗在固定间隔运行（如每 15/30 分钟 cron）时，需精确判断"从上次检查至今"是否有新活动，而非笼统的 `-mmin -30`。

```bash
# 精确：检查从 last_check 时间点至今的文件活动
find "telemetry/bot/" -newermt "2026-07-08 12:56" -type d 2>/dev/null | head -5

# 配合 stat 验证实际时间
stat -c '%y %n' "telemetry/bot/$(ls -t telemetry/bot/ | head -1)"
```

**优势**: 避免 `-mmin` 的滑窗效应——如果 cron 在 T+25min 运行，`-mmin -30` 会漏掉 T 时刻前后边界的数据，而 `-newermt` 以检查时间为锚点精确截断。

**进阶：用 Epoch 秒做数值比较**

`stat -c '%y'` 返回人类可读的时间戳（如 `2026-07-10 11:12:51.489354100`），无法在做时间差比较时直接运算。用 `stat --format='%Y'`（Unix epoch 秒）可获得纯数值时间戳，便于脚本计算：

```bash
# 获取当前 epoch 秒
NOW=$(date +%s)

# 获取最新 bot 目录的 epoch 秒
BOT_DIR=$(ls -t /c/Users/Administrator/Documents/BlastGame/telemetry/bot/ | head -1)
BOT_EPOCH=$(stat --format='%Y' "/c/Users/Administrator/Documents/BlastGame/telemetry/bot/$BOT_DIR")

# 计算相差分钟数
DIFF=$(( (NOW - BOT_EPOCH) / 60 ))
echo "Bot last activity: $DIFF minutes ago"

# 一行搞定：同时输出 epoch + 人类时间 + 文件名
stat --format='%Y %y %n' "/c/Users/Administrator/Documents/BlastGame/telemetry/bot/$BOT_DIR"
# 输出: 1783653171 2026-07-10 11:12:51.489354100 +0800 L58_71_75-T5-...
```

> **注意：** `date +%s` 在 MSYS2/git-bash 下返回的是 Unix epoch 秒，与 Linux 一致。`stat --format='%Y'` 返回文件 mtime 的 epoch 秒。两者单位相同可直接做减法。`stat -c '%Y'`（短选项）也等效，但在 MSYS 中 `-c` 和 `--format` 都支持。

#### Bot 目录内容验证（超越目录存在性检查）

有时 Bot 目录虽然存在，但其内部可能为空（批次刚创建根目录，尚未写入 CSV 数据）。更可靠的活力信号是**确认目录内有实际数据文件**。

```bash
# 检查最新 bot 目录是否包含真实 CSV 文件
find "telemetry/bot/$(ls -t telemetry/bot/ | head -1)" -name "*.csv" | head -5
# 有输出 = 有真实数据；无输出 = 空目录或刚创建

# 更彻底的检查：确认 T1-T5 各 tier 都有数据
find "telemetry/bot/$(ls -t telemetry/bot/ | head -1)" -name "*T*.csv"
# 预期输出 10+ 行（每 tier 有 ca- 和 cs- 两个 csv）
```

**实例（2026-07-08 13:26）**：`51_55-2026-07-08T12-39-10` 目录下有 `L51_55-T1-.../ca-L51_55-T1.csv`、`cs-L51_55-T1.csv` 等共 6 个 CSV 文件，说明该批次确实产出了数据。

**判定影响**：
- 目录存在 + 有 CSV → ✅ 真实批次活动
- 目录存在 + 无 CSV → 🟡 刚刚开始或目录创建中断
- 目录不存在 → ❌ 无活动

#### 特例：父目录 mtime 单独更新（子目录缺失）

**现象**: `auto-batch-result.json` 的 `outDir` 路径所指向的 bot 子目录**不存在于文件系统中**，但 `bot/` 父目录的 mtime 在相应时刻有变化。

**2026-07-07 实例**: L90 批次在 11:19 完成（`auto-batch-result.json` 的 `finishedUtc` 确认），bot 父目录 mtime 为 `11:19:57`，但 `90-90-2026-07-07T11-19-33` 子目录不存在，`ls -lt bot/` 未显示该目录。

**可能原因**:
- Unity auto-batch-trigger 内部写入 result.json 但 export 目录因某些原因（如弹窗被拦截、路径权限问题）未持久化
- 批次在 Unity 内完成但写出中途被中断（关闭弹窗、重编译等）
- `auto-batch-last-export.txt` 指向的路径与 bot/ 子目录命名不完全一致

**检查方法**:
```bash
# 确认子目录是否存在
ls -la "/c/.../telemetry/bot/" | grep "90-90.*11-19"
# 查看 bot/ 父目录 mtime（作替补信号）
stat -c '%y' "/c/.../telemetry/bot/"
# 比对 auto-batch-result.json 的 outDir 路径
cat BuildLogs/auto-batch-result.json | grep outDir
```

**判定影响**: 当 `auto-batch-result.json` 报告成功但子目录缺失时，管道可能比预期的更卡——因为上次 \"成功\" 的批次可能只有元数据写入而没有实际跑出数据。看门狗应仍视为无活动（不计为进展），同时标记\"最后批次可能未产生数据\"。

#### Phantom Path After Completion（export 虚路径模式）

> **2026-07-15 18:07 发现的新变体。** 不同于上一节（批次完全未产生数据），phantom path after completion 指批次**成功完成且产出了数据**，但 `auto-batch-last-export.txt` 随后记录了一个比实际批次时间戳**更新**的路径——且该路径在文件系统中不存在。

**实例：**
- 实际批次：`96_100-2026-07-15T16-16-57`，T1-T5 全部齐全，完成于 16:22
- Export 文件（`auto-batch-last-export.txt`，mtime=17:15）指向：`96_100-2026-07-15T17-13-21\L96_100-T2-...`
- 注意：17-13-21 比实际批次时间戳（16-16-57）**晚了 56 分钟**

**与「Bot 死在导出阶段」模式的区别：**

| 维度 | Bot 死在导出阶段 (mid-interruption) | Phantom Path After Completion (post-completion) |
|------|-----------------------------------|----------------------------------------------|
| 实际批次 | 可能未完成或仅部分完成 | **完整完成**（T1-T5 齐全，CSV 数据完整） |
| Export 时间戳 vs 批次时间戳 | export 路径在批次完成前写入，时间戳 ≈ 实际批次开始时间 | export 路径的 timestamp **晚于** 实际批次完成时间 |
| 文件系统状态 | 指向的目录可能部分存在或完全不存在 | 指向的目录**完全不存在**，但批次目录完好 |
| 含义 | 批次被中断，数据丢失 | 某个后续步骤记录了 **预测/意向路径**，而不是真实出口目录 |
| 常见时机 | 批次执行期间 Unity 崩溃、被关闭 | 批次完成后某个处理环节（如 optimizer ingestion、数据导出脚本）构造了下一个预期路径 |

**检测方法：**
```bash
# 1. 读取 export 文件
cat auto-batch-last-export.txt

# 2. 从 export 路径提取时间戳
export_ts=$(cat auto-batch-last-export.txt | grep -oP 'T\d{2}-\d{2}-\d{2}' | head -1)

# 3. 查找实际最新 bot 目录
actual_bot=$(ls -t telemetry/bot/ | head -1)
actual_ts=$(echo "$actual_bot" | grep -oP 'T\d{2}-\d{2}-\d{2}' | head -1)

# 4. 比较：如果 export 时间戳 > 实际最新目录时间戳，且 export 路径不存在
if [ "$export_ts" \> "$actual_ts" ]; then
    echo "PHANTOM PATH: export points to future path $export_ts vs actual $actual_ts"
fi

# 5. 确认 export 路径文件是否存在
export_dir=$(cat auto-batch-last-export.txt | sed 's/\\/\//g' | xargs dirname)
ls -la "$export_dir" 2>/dev/null || echo "Phantom path confirmed — directory does not exist"
```

**看门狗处理：** phantom path after completion 本身不是卡住信号（批次数据已完整产出），但它说明 export 脚本可能获取了错误的批次路径名。看门狗应：
1. 记录这一现象到 `stuck_reason`（如 `"phantom path in auto-batch-last-export.txt: points to T17-13-21 but actual latest batch is T16-16-57"`）
2. 不因此判定为卡住（仍然看最近 30 分钟 bot 目录活动）
3. 如果连续多次出现 phantom path 且批次完成后长时间无后续活动 → 可能是 ingestion 链断裂的早期信号（export 脚本试图处理下一批次但找不到正确的目录）

**下一步排查方向：**
- 检查 `auto-batch-result.json` 的 `outDir` 是否指向正确的批次路径
- 检查 `auto-batch-request.json` 是否在批次完成后被删除（正常消费）或残留（TryDelete 失败）
- 对比多个 export 时间戳：如果每次都是 phantom path，说明 export 步骤存在系统性 bug（路径构造错误）

### 3. Unity 进程健康检查

### ⚠️ 关键区分：Unity Editor (GUI) vs 头次 Unity 子进程 (Headless Batch Mode)

看门狗常犯的一个错误：用 `unity_editor_running` 单一布尔值判断整个管道的生命迹象。实际上 **两种不同的 Unity 进程** 可能同时或分别存在：

| 类型 | 检测方式 | 进程名 | 特征 | 含义 |
|------|---------|--------|------|------|
| **Unity Editor (GUI)** | `ps -W \| grep -E '^Unity\\.exe' \| grep -v Hub \| grep -v Licensing` | `Unity.exe` | 持久进程，内存 ~1-3GB，持续运行 | Editor 模式 — `PollForRequest` 循环、等待 request.json 消费 |
| **Headless Unity 实例** | `ps -W \| grep -E 'Unity\\.exe.*-batchMode'` | `Unity.exe` 含 `-batchMode` 参数 | **短暂进程**，每次批跑时由 `submit_batch_unity.py` 启动 → 编译 → 跑 bot → 退出 | **Batch mode** — 不依赖 Editor 循环，每次独立运行 |

**看门狗检测要点：**
- `tasklist` / `ps -W` 的 **默认 `grep Unity.exe` 不区分两者**——会同时匹配 Editor 和 headless 实例
- 要确认 Editor 是否存在：`ps -W | grep Unity.exe | grep -v Hub | grep -v Licensing` — 如果只看到 1-2 个 短暂 PID（存在几秒就消失），那是 headless 实例在轮换，**不是 Editor**
- **更可靠的区分：检查进程命令行参数**
  ```bash
  # Windows: wmic 可显示完整命令行
  wmic process where "name='Unity.exe'" get ProcessId,CommandLine 2>/dev/null | head -10
  # 包含 -batchMode 或 -nographics 的 → headless 实例
  # 不包含这些参数的（或含 -projectPath 但无 -batchMode）→ Editor
  ```
- **看门狗结论**：`unity_editor_running = false` + 但有 `-batch-range` bot 目录产生 = **Batch-mode 正常运行，不被视为卡住信号**。`unity_editor_running` 字段应改为记录 Editor 模式（持久进程），同时增加 `batchmode_active` 以区分。

**实例（2026-07-16 23:29）**：看门狗在 21:55 判断 `stuck=True`（Unity Editor 不存在、无新 bot 目录 5 小时），但 23:29 发现新批次目录 `L59_81-82_89_91_98-T2-2026-07-16T23-27-47.180-batch-range` 含有完整 CSV 数据。事后回溯：该时段 Unity Editor 从未运行，是 `submit_batch_unity.py` 在后台产出了这些数据。以 `unity_editor_running = false` 作为卡住判定信号在此场景下是假阳性。

### ⚠️ 关键陷阱：`ps aux` 在 git-bash 下对 Windows 进程不可见

`ps aux | grep -i unity` 在 git-bash/MSYS2 中**始终返回空**，即使 Unity.exe 正常运行。因为 git-bash 的 `ps` 只看到 MSYS/PID 命名空间内的进程（主要是 shell 及其子进程），看不到原生 Windows 进程。这是 MSYS 的已知限制。

**表现：** cron job 的终端输出中 `ps aux` 结果为空白 → 可能被误判为"Unity 已崩溃，管道停摆"。

**解决方案：必须使用 Windows 原生进程查询命令：**
- `tasklist | grep -iE '(Unity|mono|il2cpp|batch)'` — 最简洁
- `tasklist /FI "IMAGENAME eq Unity.exe" /NH` — 精确过滤
- `wmic process where "name like '%Unity%'" get name,processid` — 备用

**检查命令** (Windows/MSYS2):
```bash
# 首选（最简洁，原生 git-bash 命令）
ps -W | grep -iE '(Unity|mono|il2cpp|batch)'

# 备选
tasklist | grep -iE '(Unity|mono|il2cpp|batch)'
```

> **为什么 `ps -W` 比 `tasklist` 好：** `ps -W` 是 MSYS/git-bash 的内置命令，直接在当前 shell 进程空间运行，不需要创建新的 Windows 进程（`tasklist` 需要启动 `tasklist.exe`）。在 cron job 环境下，`ps -W` 比 `tasklist` 快约 50ms/调用，且输出格式与常规 `ps aux` 一致（PID、状态、CPU时间、命令行），更容易解析。`tasklist` 的行尾带 `\r\n` 需要额外过滤，而 `ps -W` 输出已经是 unix 格式。
>
> **注意：** `ps -W` 的 CPU 时间列（第 5 列）在 MSYS 下显示的是进程启动后的累计 CPU 秒数，格式为 ` 0:00:15`（时:分:秒）。这对判断进程是否新启动有帮助——Unity 主进程的 CPU 时间如果从上次检查大幅增长，说明正在活跃工作；长时间不变则可能空闲。**不要用 `ps aux`**（等效 `ps -W` 但默认不带 -W），它在 git-bash 下只显示 MSYS 命名空间内的进程（shell 及其子进程），看不到原生 Windows 进程，总是返回空。

**进程内存获取（配合 `ps -W` 的 PID）：**
```bash
# 用 ps -W 获取 PID，再用 tasklist 获取内存
PID=$(ps -W | grep -i Unity.exe | grep -v Hub | grep -v Licensing | grep -v PackageManager | grep -v CrashHandler | awk '{print $1}')
if [ -n "$PID" ]; then
    tasklist /FI "PID eq $PID" /FO CSV /NH | awk -F'"' '{print $5}' | sed 's/,//g'
fi
```

**关键进程解读**:

| 进程 | 含义 |
|------|------|
| `Unity.exe` | Editor 主进程 — 可能空闲也在 |
| `Unity.ILPP.Runner.exe` | **IL2CPP 构建中** — 这是活跃信号，说明在打包 |
| `UnityShaderCompiler.exe` | 着色器编译 — 背景活动 |
| `UnityPackageManager.exe` | 包管理器 |
| `Unity.Licensing.Client.exe` | 许可证验证 |
| `UnityAutoQuitter.exe` | 空闲超时退出器 |

**Unity 空闲判定**: 仅有 `Unity.exe` + `Unity.Licensing.Client.exe` + `UnityShaderCompiler.exe` + `UnityPackageManager.exe` 而无 `Unity.ILPP.Runner.exe`，且无 `monitor_bot.py` 对应进程 → Unity 很可能处于空闲等待状态。

**内存信号作为活动性指标**: 除了检查进程存在性，还应关注 Unity.exe 的内存占用变化趋势。连续两次检查间内存明显下降（如 3.2GB→1.6GB）说明引擎已完成或接近完成其处理工作，可能只是进程未退出而非活跃处理中。内存稳定的进程更可能是正在工作。

```bash
# 获取 Unity 进程内存占用（KB 单位）
tasklist /FI "IMAGENAME eq Unity.exe" /FO CSV /NH
# 输出示例: "Unity.exe","40056","Console","1","1,689,400 K" -> 1.6GB
# 提取内存数值
tasklist /FI "IMAGENAME eq Unity.exe" /NH | awk -F'"' '{print $5}' | sed 's/,//g'
```

**判定规则**:
- 内存 **稳定或增长** (相比上次检查) + 进程存在 + 日志有近期活动 → 🟢 活跃
- 内存 **明显下降** (如 3.2GB→1.6GB) + 进程仍存在 + 无新 bot 目录 + 无新日志 → 🟡 可能空闲/挂起
- 内存下降 + 无新 bot 目录 >= 1.5h → 配合其他信号确认卡住

### 4. 自动批跑触发器状态

**工作原理** (`BlastBotAutoBatchTrigger.cs`):
- 每 5 秒轮询 `BuildLogs/auto-batch-request.json` 是否存在且 mtime 更新
- 检测到新请求 → 执行批跑 → 写入 `auto-batch-result.json` → **删除** `auto-batch-request.json`
- 重复上述循环

**关键文件**:
```bash
# auto-batch-request.json — 存在 = 有未消费的请求（或正在跑）
#   （运行期间不会删除：RunBot → WriteResult → TryDelete）
#   ⚠️ 也可能**批次已结束但 TryDelete 失败** → stale request.json 残留
#     检测方法：比对 request.json mtime 与最新 bot 目录 mtime。
#     如果 request.json mtime 早于最新 bot 目录 mtime 且后者已 30min+ 无更新，
#     则 request 很可能是 stale，实际无待消费请求。
# auto-batch-result.json — 存在 = 最后完成的批次结果
# auto-batch-last-export.txt — 最后导出路径
```

> **⚠️ Stale request.json 陷阱（2026-07-10 实例）：** `auto-batch-request.json` 的 mtime 为 19:15，bot 目录 `51_54_61-63_70-*` 完成于 20:15（mtime），但 request.json 在 21:45 仍存在（未删除）。`ls -la` 显示 mtime=19:15 未变过，说明 Trigger 的 TryDelete 环节失效或异常退出。这导致看门狗误判为"有未消费请求（正在跑）"，实际批次已结束 1.5h。**判断法则：** 如果 request.json 的 mtime 早于最新 bot 目录的创建时间（从目录名或 mtime 推断），且无更新的 bot 目录出现，则视为 stale request——不计为活性信号。反之如果 request.json mtime 比任何 bot 目录都新，则是真正的待消费请求。

**检查命令**:
```bash
# request.json 不存在 = Unity 在空闲等待
ls -la BuildLogs/auto-batch-request.json       # 应不存在（已消费）
# 判断是否 stale：比对 mtime
stat -c '%y %n' BuildLogs/auto-batch-request.json 2>/dev/null
ls -lt telemetry/bot/ | head -1                     # 最新 bot 目录
cat BuildLogs/auto-batch-result.json                # 查看最后批次结果
cat BuildLogs/auto-batch-last-export.txt            # 最后输出路径
```

**判定**: `auto-batch-request.json` 不存在 + `auto-batch-result.json` 显示成功 + 超过 30 分钟无新 bot 目录 → **管道卡住，Unity 空闲等待中**。

### 5. Unity 日志分析

**主日志路径**: `BuildLogs/` 下有两个日志系列：
- `unity-launch-v{N}.log` — **主编辑器会话日志**（v2, v3, v4, v5...），保存交互式编辑会话的活动
- `unity-launch-test{N}.log` — **测试批次专用日志**（test2, test3, test4...），batchmode 或测试运行日志

⚠️ 两个系列都可能存在。**选最新的 .log 文件（按 mtime）**，不要硬编码名称：

```bash
# 选最新日志
LATEST_LOG=$(ls -t BuildLogs/unity-launch*.log 2>/dev/null | head -1)
echo "Using: $LATEST_LOG"
stat -c '%y' "$LATEST_LOG"
```

**实例（2026-07-09）**：当时最新的是 `unity-launch-v5.log`（3.4MB，mtime=06:12），表示 Unity Editor(GUI) 正在运行。而 `unity-launch-test4.log` 是 07-08 的旧测试日志（24MB，mtime=01:33）。

**查看最后操作**:
```bash
tail -30 "$LATEST_LOG"
```

**关键日志信号**:

- `"[Bot Batch] Level L(\d+) \((\d+)/49\)"` — **当前批次进度**。如 `L64 (12/49)` 表示第 12/49 关正在跑。这是最可靠的实时活动信号
- `"[Bot Batch Jenkins] 完成，最后导出目录: ..."` — 批次完成标记
- `"BlastBotAutoBatchTrigger:PollForRequest"` — 触发器在轮询（正常活动）
- `"Successfully resolved entitlement details"` — 许可证续签（背景活动）
- `"[Licensing"` — 许可证相关，不表示管道推进
- `"[Bot Batch"` (无 Level 号) — 可能是 **monitor_bot.py 检测到 export 时的日志**，不是实际批次。确认方法：检查 `auto-batch-result.json` 的 `finishedUtc` 是否为空或过期

**实时活动性判定：** 日志 mtime + tail 提取当前关卡，是比仅检查 Unity 进程存在更精细的信号。Unity 可能活着但卡在某个状态，日志的 mtime 和最后几行会暴露。

```bash
# 1. 选最新的 unity log 文件
LATEST_LOG=$(ls -t BuildLogs/unity-launch*.log 2>/dev/null | head -1)
# 2. 检查 mtime（活动性）
stat -c '%y' "$LATEST_LOG"
# 3. tail 提取当前跑的关卡
#    行如: [Bot Batch] Level L64 (12/49): 400 runs x 1 strategy = 400 games
tail -20 "$LATEST_LOG" | grep -oP 'Level L\K\d+ \(\d+/\d+\)' | tail -1
```

**判定规则：**
- mtime < 5 分钟前 + 能提取到 `Level L\d+` 行 → **Unity 正在活跃处理批次**
- mtime < 5 分钟前 + 无 `Level L\d+` 但有 `PollForRequest` 行 → Unity 在轮询等待下一请求
- mtime > 30 分钟前 → **Unity 可能卡住或已空闲**，需综合其他信号

**查看 Unity 启动时间**:
```bash
head -10 "$LATEST_LOG" | grep "Date:"
```

### 6. `_stall.json` — 批跑内部 Stall 记录

**文件**: `BuildLogs/_stall.json`

这是 **batch-runner 层**的 stall 记录，与 watchdog 的 `pipeline-progress-check.json` 互补。由 `batch-runner.py` 或 `submit_batch.py` 在单个关卡超时/卡死时写入。

```json
{
  "levels": ["51", "52", "54", ...],
  "tiers": "1,2,3,4,5",
  "run_count": 200,
  "skip_patch": true,
  "tag": "auto-round1",
  "timestamp": "2026-07-08T19:17:00",
  "stuck_at": "L82 (21/28) - 15s no log growth",
  "completed_before_stuck": 21
}
```

| 字段 | 含义 |
|------|------|
| `stuck_at` | 卡住的关卡+已完成的子任务数 |
| `completed_before_stuck` | 卡住前已完成的任务数（如 21/28 = 跑了 21 遍后卡在 L82） |
| `timestamp` | stall 发生时间 |
| `levels` | 该批次包含的所有关卡列表 |

**用途**: 不同于 `pipeline-progress-check.json`（全局管道健康检查），`_stall.json` 记录的是**单次批次执行内部**的局部卡死。检查时两个文件应交叉验证：
- 如果 `_stall.json` 存在且时间戳较新，说明 batch-runner 层已检测到卡死，即使 Unity 仍在运行
- 示例（2026-07-08 19:17）：`_stall.json` 记录了 L82 在 21/28 进度时卡死，而 watchdog 的 `pipeline-progress-check.json` 在 03:25 时却说 `stuck: false`——两者不一致，应采信 `_stall.json` 的时间戳

**检查命令**:
```bash
cat BuildLogs/_stall.json 2>/dev/null || echo "_stall.json 不存在"
```

### 7. 外部驱动进程检查

管道需要外部脚本写入 `auto-batch-request.json` 来推进。检查是否有此类进程：

```bash
tasklist | grep -iE '(python|cmd|powershell|jenkins|batch)'
```

**无匹配 = 外部驱动已停止**。Unity 虽然活着但等不到新请求。

如果看到 Python 进程，进一步确认是否与管道相关（Hermes 后台进程也会显示为 python.exe）：
```bash
wmic path win32_process where "name='python.exe'" get ProcessId,CommandLine
```

### 8. 管道进度快照检查

**文件**: `BuildLogs/pipeline-progress-check.json`

作用：记录上次检查时的快照，用于跨会话对比 `levels_done` 变化。

```json
{
  "last_check": "2026-07-09 20:05",
  "levels_done": 15,
  "recent_bot_dirs": [
    "68-68-2026-07-09T20-02-25 (modified 20:03, latest)",
    "51-52_...-2026-07-09T20-00-12 (modified 20:00)"
  ],
  "latest_bot_timestamp": "2026-07-09 20:03",
  "last_progress_update": "2026-07-07 11:43",
  "new_dirs_since_last_check": 2,
  "total_bot_dirs": 40,
  "stuck_count": 0,
  "last_stuck_alert": null,
  "done_array_count": 15,
  "stuck": false,
  "stuck_reason": "levels_done stuck at 15 since Jul 7, but bot actively running — 2 new dirs at 20:00-20:03"
}
```

> **生产示例（2026-07-09 实际写入）：** 包含全部可选字段 `done_array_count`、`stuck`、`stuck_reason`。这三个字段不是 JSON Schema 必需的，但推荐写入以便快速判断状态和自检 levels_done 一致性。

**必填字段说明：**

| 字段 | 类型 | 用途 |
|------|------|------|
| `last_check` | string | 本次检查时间，格式 `YYYY-MM-DD HH:MM` |
| `levels_done` | int | 上次读取的 `levels_done` 值，用于 delta 比较 |
| `recent_bot_dirs` | string[] | 上次看到的最近 bot 目录列表（用于检测目录是否新增） |
| `latest_bot_timestamp` | string | 上次检查时最新 bot 目录的时间戳 |
| `last_progress_update` | string | `pipeline-progress.json` 的 mtime |
| `stuck_count` | int | **必需。** 累计连续卡住检测次数。用于告警抑制（见 `看门狗投递策略` 节）。初始 0，状态变化时 reset 为 0 |
| `last_stuck_alert` | string\\|null | 上次投递卡住告警的时间。用于判断是否该升级/静默 |
| `new_dirs_since_last_check` | int | **可选**，推荐 | 上次检查以来新增的 bot 目录数量。便于快速判断趋势 |
| `total_bot_dirs` | int | **可选**，推荐 | bot 目录总数快照。验证时需容忍实时增长（用 `>=` 而非 `==`） |

**检查逻辑：**
1. 读取此文件的各字段作为**上次状态**
2. 读取当前 `pipeline-progress.json` 的 `levels_done`，比对
3. 检查 `telemetry/bot/` 最近 30 分钟新目录列表，与 `recent_bot_dirs` 对比
4. 如果 `levels_done` 未变 且 无新增 bot 目录 → `stuck_count++`
5. 如果 `levels_done` 变了 或 有新 bot 目录 → `stuck_count = 0`（恢复）
6. 更新 `pipeline-progress-check.json` 写入当前快照

---

### 8. 同关卡空转检测

**信号**: 连续两次检查发现 bot 目录的 level 前缀（如 `55-55-`）完全相同，且 `levels_done` 未增长。

```bash
# 检查两次检查间 bot 目录的 level 是否变化
# 比较 recent_bot_dirs 中的目录名前缀
```

**根因**: agent 卡住或会话中断后重启，未正确推进到下一关。恢复方法：手动检查 progress.json → 取当前 pending 关 → 提交至下一关。

**判定**: 如果连续 3 次以上检查发现 bot 目录前缀未变 → 管道在**空转**，需外部干预提交下一关请求。

### 9. 批次成功完成但无后续请求（Post-Batch Stall）

**信号：**
- `auto-batch-request.json` **不存在**（已被消费，但无新请求生成）
- `auto-batch-result.json` 存在且显示 `success: true` + 最近 `finishedUtc`
- 最近 Bot 目录的 **T1–T5 全部齐全**（批次完整完成）
- `levels_done` 多轮未变
- 最近 30 分钟无新 Bot 目录
- `pipeline-progress.json` 长时间未更新（即使批次已完成）
- `multi-tier-opt/` 长时间无更新（无结果处理）

### 实例 A（2026-07-08 16:16 — Unity 已退出的 Post-Batch Stall）

**情景：** 管道当天从 13:30 到 15:03 连续跑了 T1→T5 完整 5 档（每档 26 关），之后完全停摆。

| 信号 | 值 |
|------|-----|
| `levels_done` | 15（自 07-07 10:13 起 ~30 小时未变） |
| 最新 bot 目录 | `...-T5-...` 于 **15:03**（73 分钟前） |
| 30 分钟内新 bot 目录 | ❌ 无 |
| Unity 进程 | ❌ 已退出 |
| Python 管道脚本 | ❌ 无 |
| `pipeline-progress.json` mtime | 07-07 11:43（~28.5 小时未变） |
| `auto-batch-request.json` | 不存在 |

**诊断：** 🔴 **Post-Batch Stall**（见 §9）。批次完整产出（T1–T5 全部 CSV 齐全），但外部驱动未提交下一批请求。当日上午各级别的 T1→T5 目录间隔约 22-25 分钟，说明 Unity 工作节奏稳定，问题在驱动链。手动恢复方法见 §9「恢复步骤」。

### 实例 C（2026-07-11 03:08 — Stale-Request Stall：TryDelete 失败导致虚假活性信号）

**情景：** 管道此前经历了多次混合状态检查（July 10 01:36 为"临界状态"，因为 Unity 刚出现），到 July 11 03:08 终于确认卡住。与实例 A/B 不同，这里 `auto-batch-request.json` **仍然存在**（但 mtime 表明是旧的已完成请求），造成"有未消费请求"的假象。

| 信号 | 值 |
|------|-----|
| `levels_done` | 15（自 07-07 11:43 起冻结 >4 天） |
| 最新 bot 目录 | `51_54_61-63_70-2026-07-10T19-29-10` 于 **20:15**（6.8 小时前） |
| 30 分钟内新 bot 目录 | ❌ 无 |
| **Unity 进程** | ✅ **运行中**（PID 23228, 2.8GB）— 但无任何新输出 |
| **`auto-batch-request.json`** | ⚠️ **存在但不新鲜** — mtime=19:15，请求 `51,54,61,62,63,70` 已于 20:15 由 T5 完成。TryDelete 失败导致残留 |
| bot-batch-last-output-rel.txt | 指向 19:29 创建的目录 ✓ |
| auto-batch-last-export.txt | 指向 T5 路径 ✓（20:15 完成） |
| 管道外部驱动 | ❌ 无（Hermes cron 自身就是检测者，不是驱动者） |

**Stale Request 判定方法（2026-07-11 实测有效）：**

```bash
# Step 1: 检查 request.json 的存在性和 mtime
ls -la BuildLogs/auto-batch-request.json
# Step 2: 检查 request 内容
cat BuildLogs/auto-batch-request.json
# Step 3: 检查最新 bot 目录的时间
ls -lt telemetry/bot/ | head -1
# Step 4: 比较两者 mtime
#   如果 request mtime < 最新 bot 目录 mtime → stale
#   本例：request mtime = 19:15, bot mtime = 20:15 → request 早了 1 小时
# Step 5: 确认 bot 输出已经完成
cat BuildLogs/bot-batch-last-output-rel.txt
cat BuildLogs/auto-batch-last-export.txt
```

**演进路径：**

```
07-10 00:38 ─ T5 batch 完成（前次 cron 检测到的最晚活动）
07-10 05:53~06:24 ─ 新 bot 目录 (52_55-57_59_69_74_87_96)
07-10 11:02~16:27 ─ 58/71/75 两轮完整 T1-T5 调试
07-10 14:04~14:35 ─ 58_71_75 汇总目录
07-10 14:52~16:27 ─ 两轮 L58-only T1-T5 调试
07-10 17:35~17:58 ─ 58-58 汇总
07-10 19:15 ─ 提交 51,54,61,62,63,70 请求 (request mtime)
07-10 19:29~20:15 ─ T1→T5 全跑完 (bot 目录名含 19:29, T5 完成于 20:15)
07-10 20:15~07-11 03:08 ─ 6.8 小时无任何活动
07-11 03:08 ─ 首次确认为 STUCK (stuck=True)
```

**关键区别 vs 实例 A/B：**
- 与实例 B 一样 Unity 仍在运行，但 request.json 也未删除（A 和 B 的 request 都不存在）
- request.json 存在容易让看门狗误判为"有未消费请求（正在跑）"——但它的 mtime 比最新 bot 目录还早 1 小时
- `bot-batch-last-output-rel.txt` 和 `auto-batch-last-export.txt` 都已指向完成的 T5，confirm 批次已结束
- 所有 bot 活动都是针对已"done"关卡（51,54,61,62,63,70）或 ggk 关卡（58,71,75）的**重跑验证**——没有对 pending 关卡（89,90,91,95,99,100）提交过请求

**诊断：** 🔴 **Stale-Request Stall**（Post-Batch Stall 变体，§9 子类）。`TryDelete` 环节失效导致 request.json 残留，掩盖了驱动链断裂的事实。恢复步骤与 §9 相同——清除残留 request.json → 检查最新 bot 数据 → 提交下一批新请求。此例同时揭示了另一个根本问题：管道一直在重跑已完成/改关卡，从未推进到 pending 关。

**📌 判定提示：** 当 request.json 存在但 **它的 mtime 早于最新 bot 目录的创建时间**（且无更新的 bot 目录出现）时，必须视为 stale。不要只看"request 存在 = 有未消费请求"——要比较 mtime。这是看门狗最容易犯的两类错误之一（另一类是 `levels_done` 冻结 + Unity 运行 = 管道活跃）。

### 实例 D（2026-07-13 21:53 — Stale-Request Stall 变体：TryDelete 失败 + Unity 已退出）

**情景：** 与实例 C 相同的是 TryDelete 环节失效导致 stale request.json 残留——但此处 Unity **已经退出**（不是仍在运行）。管道完成了当天的最后一轮批跑（21:07-21:12 处理 54/90/93 的 T1-T5），随后 Unity 进程消失，留下 21:01 写入的 request.json 未被删除。这是实例 C（stale + Unity 运行）与实例 A（Unity 退出 + request 不存在）的组合变体。

| 信号 | 值 |
|------|-----|
| `levels_done` | 15（自 07-07 起冻结 6 天） |
| 最新 bot 目录 | `54_90_93-2026-07-13T21-05-59` — 5 个 T1-T5 子目录齐全，含完整 CSV 数据 |
| 30 分钟内新 bot 目录 | ❌ 无（最后活动 21:12，距今 41 分钟） |
| **Unity 进程** | ❌ **已退出**（不同于实例 C 的 Unity 仍在运行） |
| **`auto-batch-request.json`** | ⚠️ **存在但 stale** — mtime=21:01，内容 `54,90,93`，与最新 bot 目录同关卡。TryDelete 在批次完成后失效 |
| CSV 完整性 | ✅ T1-T5 全部齐全（10+ 个 CSV 文件） |
| 管道外部驱动 | ❌ 无 |

**时间线：**
```
19:30 ─ batch 54_63_68_89-90_93-94_98 (当前 Unity 会话)
19:54 ─ batch 54_89-90_93_98 (Unity 在这一轮前后重启过)
20:51 ─ batch 54_89-90_93
21:01 ─ auto-batch-request.json 写入（54,90,93）
21:05~21:12 ─ batch 54_90_93 T1→T5 完成（Unity 正常处理中）
21:12~21:53 ─ Unity 退出，request.json 残留，无新活动
```

**诊断：** 🔴 **Stale-Request Stall（Unity 已退出变体）**。与实例 C 的检测方法相同——request.json mtime(21:01) 早于最新 bot 目录的 T5 完成时间(21:12) → stale。但本例 Unity 已不在，即使清除残留 request.json 也无法自动恢复——需要先重启 Unity，再提交新请求。

**与实例 C 的关键区别：**
| 特征 | 实例 C（07-11） | 实例 D（07-13） |
|------|---------------|---------------|
| Unity 进程 | ✅ 仍在运行（空闲等待） | ❌ 已退出 |
| 恢复前提 | 清除 request.json → 提交下一批 | **先重启 Unity** → 清除残留 → 提交下一批 |
| 迷惑性 | request.json 存在让人误以为\"在跑\" | 无 Unity 进程明确显示问题，但 stale request 掩盖了真正的断点（TryDelete 失败） |
| 看门狗处理 | stuck_count++ 按标准规则 | 同实例 C，但 `stuck_reason` 应注明显式恢复路径 |

**📌 判定提示（补充）：** 当 request.json 存在但 Unity 进程已退出时，request.json **一定是 stale 的**（Unity 不在就不可能消费请求）。此时不要浪费时间执行 §4 的 request mtime 比对——直接判 stale + Unity 已退出，走重启恢复路径。

---

### 实例 B（2026-07-08 18:06 — Unity 仍在运行的 Post-Batch Stall）

**情景：** 同一批 T1→T5 批次当天下午跑完（15:03），但到 18:06 仍无后续活动。与实例 A 的区别是 Unity Editor **并未退出**。

| 信号 | 值 |
|------|-----|
| `levels_done` | 15（自 07-07 ~31 小时未变） |
| 最新 bot 目录 | `...-T5-...` 于 **15:03**（3h+ 前） |
| 30 分钟内新 bot 目录 | ❌ 无 |
| **Unity 进程** | ✅ **仍在运行**（PID 71260，已启动 ~16.5h，含 Unity.ILPP.Runner 等子进程） |
| Python 管道脚本 | ❌ 无（仅 Hermes 后台 pythonw.exe） |
| `pipeline-progress.json` mtime | 07-07 11:43（~30 小时未变） |
| `auto-batch-request.json` | 不存在 |
| 当日 bot 活动 | 13:30~15:03 T1→T5 完整 5 轮（约 22-25min 间隔）|

**关键区别：** Unity 仍然活着，但处于**空闲等待**状态——没有新 request.json 给它消费。Unity 启动已超 16 小时，说明不是刚重启的意外停摆，而是驱动链断开了几个小时后的持续空闲。

**诊断：** 🔴 **Post-Batch Stall（Unity 空闲变体）**。Unity 活得好好的（有 UnityPackageManager、ILPP 进程），但没有 request 可消费。最迷惑人的是：初学者可能认为 Unity 进程在就等于管道在运行，其实 Unity 只是在空等。

**📌 判定提示：** 如果只看 Unity 进程存在性，本例会被误判为 🟢 正常运行。必须穿透 Unity 活着的假象：
1. **`auto-batch-request.json` 不存在** → 没有可消费的请求
2. **`pipeline-progress.json` mtime 与最新 bot 目录的时间差** → 本例差 ~27h，说明 ingestion 已断裂
3. **最新 bot 目录的时间** → 3h+ 前，说明不是批次间正常间隙
4. **当日 bot 活动模式** → 前一次爆发是连续的 5 轮（T1→T5 每 22-25min），之后突然静默 3h+，远超爆发间歇（正常 40-60min），符合 Stall

**恢复步骤：** 与 §9 相同。

---

### Mixed State → Full Stall 自然演进

**发现（2026-07-10 07:06）：** Mixed State（§11）不是稳定态——当 Bot Runner 最终完成其最后一批工作且无新请求提交时，它会自然演进为 Full Stall。

**演进轨迹：**

```
Stage 1: Mixed State       — Bot 产出数据，评估链断裂，levels_done 冻结
Stage 2: Bot 最后一批完成  — verify-round3 T1-T5 齐全，无新 request
Stage 3: Unity 退出        — 无请求可消费 → Unity 空闲 → 被 AutoQuitter 或用户关闭
Stage 4: Full Stall        — 无 Unity、无驱动、levels_done 冻结、无新 bot 目录
```

**实例（2026-07-10 07:06 — Mixed State → Full Stall）：**

| 检查时间 | levels_done | 最新 bot 目录 | Unity 进程 | 判定 |
|---------|------------|-------------|-----------|------|
| 06:28 | 15 | verify-round3 T5 完成（2 分钟前） | ✅ PID 40056（1.8GB） | Mixed State（bot 活跃） |
| 07:06 | 15 | 同上（42 分钟前） | ❌ 已退出 | 🔴 **Full Stall** |

**关键特征：**
- 06:28→07:06 这 38 分钟内，Unity 进程退出了，但没有新的 pipeline 活动
- verify-round3 的 `auto-batch-request.json` 在 05:47 被消费后未被重新生成
- 所有 T1-T5 CSV 已齐全，数据就绪但评估链从未运行去读这些数据
- `pipeline-progress.json` 停留在 07-07 11:43（67 小时未变）

**看门狗处理：**
1. 第一次检测到 Unity 退出 + levels_done 冻结 → 判 `stuck = true`
2. `stuck_reason` 应包含演进路径："Mixed State persisted → bot runner finished last batch → Unity exited → Full Stall"
3. `stuck_count` 从 0→1（首次卡住）
4. 这与 §9 Post-Batch Stall 的区别在于：§9 中 Unity 通常在批次完成后仍运行（等待下一请求），而本模式的标志是 Unity 已退出。

### 实例（2026-07-08 早上 — 通宵批次 Post-Batch Stall）：
- `levels_done` 停留在 **15**（>18 小时未变）
- `pipeline-progress.json` 最后修改 **07/07 11:43**（>17 小时）
- `auto-batch-request.json` 不存在（已消费，未生成新请求）
- 自 T5 完成后 **56 分钟无任何活动**

**根因链条：**
```
外部驱动（agent/脚本）提交 request
  → Unity PollForRequest 拾取并执行批次
  → T1→T2→T3→T4→T5 全部完成 ✅
  → auto-batch-request.json 被删除（消费完毕）
  → 等待外部驱动提交下一请求
  → ❌ 外部驱动未运行 / 会话中断 / 脚本未触发
  → 管道永久停留在"等待下一请求"状态
```

> **⚠️ stuck_count 陷阱: 本次会话（2026-07-08 16:16）的看门狗检查仍漏写了 `stuck_count` 字段。** 此前 checkpoint 已有 `last_check`, `levels_done`, `recent_bot_dirs`, `latest_bot_timestamp`, `last_progress_update` 五个字段，唯独缺 `stuck_count`——与新生成的检查点完全一致。说明看门狗 agent 每次重新构造 JSON 时天然遗忘此字段。
> **根因：** agent 的 cron 实现从任务描述中得知 `levels_done` 是必读字段，但未被告知 `stuck_count` 也是必写字段。由于该字段不在 JSON 示例中显式展示（watchdog doc 的示例在 §7，但 agent 可能不读全文），每次都掉坑。
> **修复：** 看门狗必须在首次写入 checkpoint 时就包含 `stuck_count: 0`。参见 `references/checkpoint-schema.md` 完整 schema 和本文件 §「看门狗投递策略」的检查逻辑。

**特征：** 区别于 Section 10 的"全部超时"模式，此模式中 **批次本身运行成功**，问题在于驱动链断开。

**识别方法：**

```bash
# 1. 确认最后批次是否完整完成
ls -la "/c/Users/Administrator/Documents/BlastGame/telemetry/bot/$(ls -t /c/Users/Administrator/Documents/BlastGame/telemetry/bot/ | head -1)/"
# 应有 5 个子目录 L*-T1-* ... L*-T5-*，全部齐全

# 2. 确认 result.json 状态
cat /c/Users/Administrator/Documents/BlastGame/BuildLogs/auto-batch-result.json 2>/dev/null
# 应有 success: true + finishedUtc

# 3. 确认 pipeline-progress.json 未对应更新
cat /c/Users/Administrator/Documents/BlastGame/BuildLogs/pipeline-progress.json | grep levels_done

# 4. 检查外部驱动是否存在（Python Hermes 后台进程仍监听？）
tasklist | grep -i python
```

**判定影响：**
- `levels_done` 未更新 + Bot 批次完整完成 = **数据已就绪但未消费**
- 这不是 Unity 端的问题，而是 **外部驱动/Agent 端断连**
- 管道需要 **人工恢复驱动**：读取最新 Bot 数据 → 更新 levels_done → 提交下一批请求

**恢复步骤：**
1. 读取最新 Bot 目录的 campaign-attempts.csv 获取各 Tier 配置和 WR 数据
2. 在 `tuning-records.md` 记录结果（如果该批次是针对改关卡/待确认关的重测）
3. 手动更新 `pipeline-progress.json`：将新完成的关卡加入 `done` 数组，递增 `levels_done`，从 `pending` 数组移除
4. 提交下一批请求（写 `auto-batch-request.json`），或结束本范围

---

### 10. 批跑全部超时→改关卡，无下一批请求

**信号**：
- `auto-batch-request.json` 不存在
- `auto-batch-result.json` 存在且显示上一批已完成
- `batch-runner.log` 显示全部关卡均 `TIMEOUT → 改关卡`
- `levels_done` 多轮未变
- 最近 30 分钟无新 bot 目录
- `monitor_bot.py` 进程可能存活但处于 `S (sleeping)` 状态（非 `R (running)`）

**识别方法**:\n\n```bash\n# 1. 读 batch-runner.log 确认最后一批状态\ncat BuildLogs/batch-runner.log\n# 输出示例:\n#   === BATCH RUNNER START ===\n#   Pending: 6 levels\n#   Levels: ['89', '90', '91', '95', '99', '100']\n#   \n#   [1/6] L89\n#     patched L89\n#     submitted l89-r1\n#     TIMEOUT (600s)          ← submit_batch.py 的 wait_consumption 超时（Unity 未消费 request）\n#     FAILED → 改关卡\n#   ...\n#   [6/6] L100\n#     ...\n#   === BATCH COMPLETE ===\n#   Done: 15  改关卡: 44   Remaining: 0\n\n# 2. 交叉验证：batch-runner.log 的 pending 列表 vs pipeline-progress.json 的 pending 数组\ncat BuildLogs/batch-runner.log | grep \"Levels:\"\ncat BuildLogs/pipeline-progress.json | python3 -c \"import sys,json; print(json.load(sys.stdin)['levels'].get('pending',[]))\"\n# 如果 batch-runner 已处理但 progress.json 未更新 → ingestion 链断裂\n\n# 3. Remaining: 0 意味着 batch-runner 已处理完所有关卡，无新关卡可推进\n#    管道进入\"改关卡全额消耗\"状态——所有结果要么 done 要么 ggk。\n#    batch-runner 不会再自动生成下一批请求。\n\n# 4. 检查 monitor_bot.py 进程状态\ncat /proc/<pid>/status | grep State\n# 示例输出: State:  S (sleeping)   ← 活着但空闲\n# 正常应有活动时: State:  R (running)\n\n# 5. 确认是否为新状态而非旧监控残留\nls -la BuildLogs/auto-batch-request.json    # 应不存在\ncat BuildLogs/auto-batch-result.json         # 应有 success: true 和最近的 finishedUtc\n```\n\n**提交日志格式详解（2026-07-14 实例）：**\n- `patched L{N}` = 已修改该关卡的 asset 配置\n- `submitted l{N}-r1` = 已写入 `auto-batch-request.json`\n- `TIMEOUT (600s)` = `wait_consumption(600s)` 超时，request 未被 Unity 消费（600s = 10 分钟默认超时）\n- `FAILED → 改关卡` = 关卡标记为 ggk（不再继续尝试）\n- `Done: X 改关卡: Y Remaining: 0` = 处理总结：X 关已完成，Y 关标记为改关卡，**无剩余关卡可处理**\n\n**关键诊断：`Remaining: 0` 的管道后状态。** 当 batch-runner 处理完所有 pending 关（即使全部超时），管道进入\"待人工介入\"状态：\n- `pipeline-progress.json` 可能仍显示旧的 `pending` 列表（因为 batch-runner 不更新该文件）\n- 交叉验证：比较 `batch-runner.log` 的 `Levels:` 值与 `pipeline-progress.json` 的 `pending` 数组\n- 检测命令：`grep \"Levels:\" BuildLogs/batch-runner.log` 看是否还有未处理的关\n- submit_batch.py 可能仍在为其他关生成请求，但全部会因 Unity 缺失而超时（见 §15）

**根因**: 最后一批次的所有关卡都因超时被标记为"改关卡"（需人工重调），但 pipeline 未能自动生成下一批请求。pipeline 处于"待决策"状态——所有 pending 关已处理，下一关序列为空，需外部决定是继续调已标记的改关卡还是结束本范围。

**判定**: 连续两次检查均满足以上条件 → **管道卡住，pipeline 处于"改关卡死锁"状态**。需人工检查改关卡列表并决定下一步行动（继续重调或关闭范围）。

### 11. Mixed State — Bot Runner Active but Evaluation Dead

> **关键发现（2026-07-10）：** 管道可以处于一种**混合状态**——Bot 测试器在正常工作、产出数据，但评估/晋级链（读取 bot 结果 → 更新 levels_done → 写入 pipeline-progress.json）已死亡多日。这是一种比全卡死更隐蔽的故障模式。

**信号集：**

| 信号 | 状态 | 含义 |
|------|------|------|
| 最近 30 分钟有新 Bot 目录 | ✅ 有 | **Bot 正在产出数据**（Unity PollForRequest 循环正常） |
| Bot 目录内含完整 T1-T5 CSV | ✅ 是 | 批次正常完成，数据有效 |
| `levels_done` | ❌ 多日未变（67h+） | 评估链未运行 |
| `pipeline-progress.json` mtime | ❌ 多日未变（67h+） | ingestion 脚本最后一次写回是几天前 |
| `multi-tier-opt/` 最新结果 | ❌ 20h+ 前 | 优化器也未消费新数据 |
| Unity 进程 | ✅ 运行中（稳定内存） | Unity 活得好好的，在等待或消费 request |
| `auto-batch-request.json` | 存在 / 不存在均可 | 可能仍在等待消费，或已被消费等待下一请求 |

**根因：** Bot 运行循环（Unity Editor 内 BlastBotAutoBatchTrigger）与 评估写入循环（外部 Agent/脚本驱动）是**两条独立的链**。其中一条断裂但另一条仍在工作的状态就是 Mixed State。具体地：
1. Unity 的 `PollForRequest → RunBot → WriteResult → TryDelete` 循环正常，能消费 request 并产出数据
2. 但外部的 Agent/脚本（负责读 bot 数据 → 判定胜率 → 更新 levels_done → 写 pipeline-progress.json → 生成下一批 request）已停止工作
3. 结果：Bot 目录越来越多但进度文件永远停在旧值

**实例（2026-07-10 06:28）：**
- `levels_done=15` 自 07-07 11:43 起 **67 小时未更新**
- 但当天 06:24 刚完成一轮 `verify-round3` 批跑（9 关 × T1-T5 完整 CSV 数据）
- Unity PID 40056 持续运行，auto-batch-request.json 在 05:47 被修改
- Bot 目录有 44 个，当天新增 1 个

**识别方法（逐项检查）：**

```bash
# 1. 确认 Bot 目录是否真的在最近产出
ls -lt telemetry/bot/ | head -3

# 2. 确认 CSV 数据完整性（T1-T5 齐全？）
find "telemetry/bot/$(ls -t telemetry/bot/ | head -1)" -name "*.csv" | wc -l
# >10 = T1-T5 完整

# 3. pipeline-progress.json mtime vs 最新 bot 目录时间差
stat -c '%y' BuildLogs/pipeline-progress.json
# 如果差距 >24h → 评估链断裂

# 4. 检查 request 文件是否在批次完成后仍存在（未被消费）
cat BuildLogs/auto-batch-request.json 2>/dev/null
# 如果存在且内容与最新 bot 目录的关卡匹配 → 下次 request 已提交等待消费
# 如果不存在 → Unity 空闲，等待外部驱动写入下一 request

# 5. 检查 Unity 日志是否活跃（最近 5 分钟有输出）
LATEST_LOG=$(ls -t BuildLogs/unity-launch*.log 2>/dev/null | head -1)
if [ -n "$LATEST_LOG" ]; then
    stat -c '%y' "$LATEST_LOG"
    tail -5 "$LATEST_LOG" | grep -iE '(Bot Batch|PollForRequest)'
fi
```

**与 Post-Batch Stall（§9）的区别：**

| 特征 | Mixed State | Post-Batch Stall |
|------|------------|------------------|
| Bot 正在产出新数据？ | ✅ **是**，最近 30 分钟可能有新目录 | ❌ 最后一个批次是几小时前完成的 |
| `pipeline-progress.json` 落后于 Bot 数据？ | ✅ **显著落后**（天级差异） | ✅ 也可能落后，但时段较短 |
| `auto-batch-request.json` 存在？ | 可能存在（有等待消费的请求） | 不存在（已被消费，无新请求生成） |
| 根本问题 | 评估/晋级链断裂 | 外部驱动未提交下一批请求 |
| 恢复方法 | 修复评估链：读最新 bot 数据 → 判定 → 写进度 → 提交下一请求 | 提交下一批请求 |

**看门狗投递策略：**

当检测到 Mixed State 时，看门狗应：
1. 判定 `stuck = False`（因为 Bot 正在活动，不是全卡死）
2. `stuck_reason` 描述为混合状态并说明评估链断裂
3. **不递增 `stuck_count`**（管道局部仍有活性，不适合按全卡住抑制）
4. 如果连续 3+ 次检查评估链仍未恢复 → 升级为 🔴 告警（需要人工修复评估脚本）

**恢复步骤：**
1. 读取最新 Bot 目录的 `campaign-summary-*.csv` 获取各 Tier 胜率数据
2. 按 judgment-rules.md 的合格判定表评估各关卡
3. 对合格关卡：更新 `pipeline-progress.json`（加入 `done` 数组，递增 `levels_done`）
4. 对需重测关卡：标记 `ggk`（改关卡）
5. 提交下一批 request（写入 `auto-batch-request.json`）
6. 或启动评估脚本恢复自动处理

### 演进：Mixed State → Full Stall

当 Mixed State 持续且 bot runner 完成最后一批工作后，管道会自然演进为 Full Stall。详见 §「Mixed State → Full Stall 自然演进」。

---

### 12. Burst Activity Pattern — 间歇性活动检测

**现象**: 管道在短时间内（5-15 分钟）集中产出多个 bot 目录（一批），然后进入 40-60 分钟的空闲期，之后可能再爆发下一批。这种"爆发-空闲"节奏可能重复多次。

**实例（2026-07-08）**:
- 12:32–12:42 (10min): 产出 `61-61-...` 和 `51_55-...` 两个 bot 目录，各带 T1/T3/T5 CSV 数据
- 12:42–13:26 (44min): 无新活动
- 看门狗在 13:26 运行时，严格 30 分钟窗口内无新目录，但实际当天有 2 次真实批次产出

**根因推测**:
- 外部驱动脚本（batch-runner.py / orchestrator）按关提交后进入等待状态，待 Unity 跑完该关再提交下一关
- Unity 跑一关（含 3–5 个 tier）需要 5–15 分钟
- 驱动脚本提交完一批后自身退出或休眠，等待下一次 cron/定时器触发
- 这是**正常工作流**，不是卡住——只是节奏慢

**识别方法**:

```bash
# 1. 查看当天全部 bot 目录，不限于 30 分钟窗口
ls -lt telemetry/bot/ | grep "$(date +%Y-%m-%d)" | head -20

# 2. 查看目录内容验证确为数据产出
for d in $(ls -t telemetry/bot/ | grep "$(date +%Y-%m-%d)" | head -5); do
    csv_count=$(find "telemetry/bot/$d" -name "*.csv" 2>/dev/null | wc -l)
    echo "$d → $csv_count csv files"
done

# 3. 检查 pipeline-progress.json mtime（即使 levels_done 未变，mtime 可能已变）
stat -c '%y' BuildLogs/pipeline-progress.json

# 4. 查看 auto-batch-request.json — 存在 = 有等待消费的请求
ls -la BuildLogs/auto-batch-request.json 2>/dev/null && echo "EXISTS (pending)" || echo "NOT EXISTS (idle/idle-burst)"
```

**与真正卡住的区别**:

| 特征 | Burst 模式（正常） | 真正卡住 |
|------|-------------------|---------|
| levels_done 变化 | 可能长时间不变（数据收集期） | 长时间不变 |
| **当天有 bot 目录?** | ✅ 有，今天产出的 | ❌ 无，最后目录是昨天或更早 |
| CSV 文件完整性 | ✅ T1-T5 级都有数据 | ❌ 目录存在但无 CSV 或不全 |
| `auto-batch-request.json` | 可能存在（等待消费）或不存在（批次间间隙） | 不存在且长时间无变化 |
| `pipeline-progress.json` mtime | 可能更新（驱动脚本写回进度） | 超 24h 未更新 |
| 过去 2 小时内有活动? | ✅ 有（检查 2h 窗口而非 30min） | ❌ 无 |

**看门狗处理建议**:

当 `levels_done` 未变化但当天有 bot 活动时，看门狗应按以下逻辑处理而非直接判卡住：

1. 放宽时间窗口：检查**过去 2 小时**而非 30 分钟内的活动
2. 优先检查当天是否有 bot 目录：`ls -lt telemetry/bot/ | grep "$(date +%Y-%m-%d)"`
3. 检查 CSV 文件完整性确认批次真正完成
4. 检查 `auto-batch-request.json` 和 Unity 日志判断驱动是否还在工作
5. 只在 **当天无 bot 目录 + 24h 无 levels_done 变化**时判卡住

---

### 13. Multi-Tier Optimizer 活动检测（递归扫描子目录）{#multi-tier-opt-scan}

> **⚠️ 关键发现（2026-07-12）：** `multi-tier-opt/` 的**父目录 ctime 不代表子目录的最新活动时间**。Top-level 目录在创建完成后不再更新 ctime，但其内部子目录会随着每关优化结果写入而获得新的 ctime。只检查父目录 ctime 会导致优化器明明在运行却被判定为已停滞。

**问题实例（2026-07-12 03:58 检查）：**

| 检查对象 | ctime | 判断 |
|---------|-------|------|
| `multi-tier-opt/` 最新上层目录 | 2026-07-11 14:22（13.6h 前） | ❌ 误判为停滞 |
| 同一目录下的子目录 `90-2026-07-12T03-49-37` | **2026-07-12 03:49（9 分钟前）** | ✅ 实际活跃 |

该目录内部链式产出了 11 个子目录，从 07-11 15:37 → 07-12 03:49 持续写入，父目录 ctime 却从未更新。

**根因：** 优化器（`multi-tier-opt.py` 或类似脚本）每次创建新的子目录（如 `90-2026-07-12T03-49-37/`）写入 `phase0_prior.csv`，但这些子目录是在已存在的父目录内创建的。父目录 ctime 保留的是父目录本身的创建时间，不随内部子目录的创建而更新。

**检测方法（两步递归扫描）：**

```bash
# Step 1: 找到最新（按 ctime）的 multi-tier-opt 上层目录
LATEST_OPT_PARENT=$(ls -lt --time=ctime "/c/Users/Administrator/Documents/BlastGame/telemetry/multi-tier-opt/" | head -2 | tail -1 | awk '{print $NF}')
# Step 2: 在该目录内按 ctime 排序子目录，取最新
OPT_DIR="/c/Users/Administrator/Documents/BlastGame/telemetry/multi-tier-opt/$LATEST_OPT_PARENT"
LATEST_OPT_CHILD=$(ls -lt --time=ctime "$OPT_DIR" | grep "^d" | head -1 | awk '{print $NF}')
if [ -n "$LATEST_OPT_CHILD" ]; then
    CHILD_EPOCH=$(stat --format='%Y' "$OPT_DIR/$LATEST_OPT_CHILD")
    NOW=$(date +%s)
    DIFF=$(( (NOW - CHILD_EPOCH) / 60 ))
    echo "Optimizer last activity: $DIFF minutes ago (in $LATEST_OPT_CHILD)"
fi
```

**或使用 Python heredoc 遍历全部顶层目录的子目录：**

```bash
python3 << 'PYEOF'
import os, datetime

opt_dir = r"C:\Users\Administrator\Documents\BlastGame\telemetry\multi-tier-opt"
now = datetime.datetime.now()
newest = None

for top in os.listdir(opt_dir):
    top_path = os.path.join(opt_dir, top)
    if not os.path.isdir(top_path):
        continue
    for sub in os.listdir(top_path):
        sub_path = os.path.join(top_path, sub)
        if not os.path.isdir(sub_path):
            continue
        ctime = os.path.getctime(sub_path)
        if newest is None or ctime > newest[1]:
            newest = (sub_path, ctime, sub)

if newest:
    ts = datetime.datetime.fromtimestamp(newest[1]).strftime("%Y-%m-%d %H:%M")
    minutes_ago = (now - datetime.datetime.fromtimestamp(newest[1])).total_seconds() / 60
    print(f"OPT_ACTIVE=True|path={newest[2]}|ctime={ts}|min_ago={minutes_ago:.0f}")
else:
    print("OPT_ACTIVE=False")
PYEOF
```

**看门狗集成：**

在看门狗检查步骤中，将此项作为独立活性信号：

```python
# 检查 multi-tier-opt 子目录活动
opt_active = check_opt_subdirs()  # True if any subdir ctime within 30 min

if opt_active and not bot_active:
    # Optimizer 在跑但 Bot 已停 → 管道部分运行（优化阶段存活）
    stuck = False
    stuck_reason = f"Bot pipeline dead since {bot_last}; optimizer active {opt_min_ago}m ago in {opt_subdir}"
```

**更新诊断信号表 — 新增优化器信号：**

| 信号 | 优先级 | 含义 |
|------|--------|------|
| `multi-tier-opt/` 子目录 ctime < 30 分钟前 | 🟢 低→中 | **Optimizer 正在产出结果** — 即使 Bot 管道已停，管道优化阶段仍在工作。这是部分活跃信号，不应判为全卡住 |
| `multi-tier-opt/` 子目录 ctime > 2 小时前 | 🟡 中 | 优化器也可能已停滞，需结合 Bot 管道状态综合判定 |
| `multi-tier-opt/` 父目录 ctime 旧但子目录有更新 | ⚠️ 特殊 | **父目录 ctime 不可靠** — 必须递归检查子目录。盲目相信父目录 ctime 是典型错误 |

**对 stuck 判定的影响：**

| 场景 | Bot 30min 内 | Opt 30min 内 | stuck | 实际解读 |
|------|-------------|-------------|-------|---------|
| 优化器在跑 | ❌ 无 | ✅ 有 | `false` | 管道部分存活：Bot 死亡，Optimizer 在其数据上工作 |
| 双活 | ✅ 有 | ✅ 有 | `false` | 管道完全正常 |
| 双停 | ❌ 无 | ❌ 无 | `true` | 管道完全卡死 |
| Bot 刚死后优化器有活动（但>30min） | ❌ 无 | ❌ 无但`>30min<2h` | `false`（暂缓判定） | 优化器可能正在消化最后一批数据，等待下次检查 |

**⚠️ 常见的错误：**

- **只扫父目录不递归子目录** — `stat --format='%Y' "telemetry/multi-tier-opt/$(ls -t telemetry/multi-tier-opt/ | head -1)"` 得到的是父目录的 ctime，不是内部最新活动的 ctime。必须走进去看子目录。
- **误以为父目录 ctime 没有子目录新就是"浪费"** — 实际上是文件系统的正常行为。子目录被创建时父目录的 ctime 是否更新取决于目录项修改发生在哪里。看门狗不能依赖这个行为。
- **看到 opt 有活动就认为 levels_done 会更新** — 优化器写结果到 `multi-tier-opt/` 但**不修改 `pipeline-progress.json`**。`levels_done` 的更新需要另一个脚本（评估链）去读优化结果并写回 progress。优化器活跃 ≠ levels_done 会自增。这是两条独立链。

### 13.1 优化器批量顺序处理节奏看门狗

> 2026-07-12 实测观察，多关批量优化器在一个批次内按顺序逐关处理，各阶段耗时约 1-2 小时/关，看门狗需要据此调整超时窗口。

**目录结构模式（单次批量）：**
```
multi-tier-opt/{batch_name}/
  ├── 51-2026-07-11T14-22-58/     ← 第 1 关
  │     ├── phase0_prior.csv       ← 探针阶段
  │     ├── phase1_raw.csv         ← Phase1 仿真
  │     ├── phase1_reachability.csv
  │     ├── phase2_candidates.csv  ← Phase2 候选
  │     ├── sensitivity.csv        ← 灵敏度分析
  │     ├── summary.csv            ← 汇总（关完成标记）
  │     └── detail.csv             ← 详细结果
  ├── 54-2026-07-11T15-37-36/     ← 第 2 关
  ├── 63-2026-07-11T16-34-59/     ← 第 3 关
  ├── ...
  └── 98-2026-07-12T08-40-36/     ← 当前处理中
        └── phase0_prior.csv       ← 仅含 phase0，尚未完成
```

**典型处理节奏（2026-07-11~12 实测）：**

| 时段 | 处理的关 | 耗时 | 备注 |
|------|---------|------|------|
| 14:22~15:37 | L51 | ~1h15m | 批次开始 |
| 15:37~16:34 | L54 | ~57m | |
| 16:34~18:16 | L63 | ~1h42m | |
| 18:16~19:38 | L65 | ~1h22m | |
| 19:38~21:35 | L68 | ~1h57m | 慢速 |
| 21:35~23:12 | L74 | ~1h37m | |
| 23:12~01:26 | L77 | ~2h14m | 过夜变慢 |
| 01:26~03:06 | L82 | ~1h40m | |
| 03:06~03:21 | L86 | ~15m | 🟢 快速（可能数据量小）|
| 03:21~03:49 | L89 | ~28m | 🟢 快速 |
| 03:49~05:02 | L90 | ~1h13m | |
| 05:02~05:46 | L92 | ~44m | |
| 05:46~07:14 | L93 | ~1h28m | |
| 07:14~08:40 | L94 | ~1h26m | 最后阶段（sensitivity 08:05→summary 08:40）|
| 08:40~ | L98 | 进行中 | 仅 phase0_prior 写入 |

**规律总结：**
- **典型耗时**：1~2 小时/关，平均约 **1.5 小时**
- **极端值**：快时 ~15-30 分钟（少数关），慢时 ~2h+（数据量大的关）
- **总时长**：15 关的批量约 **15-30 小时** 完成
- **阶段信号**：`phase0_prior.csv` 生成 = 关开始处理；`summary.csv` 生成 = 关完成
- **续跑特性**：优化器不会跳过未处理的关——即使上一关(s)未处理，也会按顺序处理下一个可处理的关（L98 在 L94 之后立即开始，跳过了 L94 旁边但不在本批的 L97）

**看门狗判定建议：**

| 最优子目录 mtime 窗口 | 判定 | 解读 |
|----------------------|------|------|
| < 30 分钟前 | 🟢 活跃 | 优化器正在高效处理下一关 |
| 30~120 分钟前 | 🟡 警惕但暂不判死 | 可能是慢关的正常间隔（最长 ~2h），等待下次检查确认 |
| > 2 小时前 | 🔴 可能停滞 | 超过最慢单关的记录上限，需结合其他信号综合判定 |
| > 2 小时前 + 无 phase0_prior 更新 | 🔴 停滞 | 最后处理的关只有旧阶段数据无推进，优化器可能卡死 |

**与其他管道组件的联动判定：**

| 场景 | Bot | Optimizer | progress.json | 判定 |
|------|-----|-----------|---------------|------|
| 正常优化阶段 | ❌ 无 | ✅ <30min | ❌ 未更新 | 🟢 优化器在工作，Bot 阶段尚未轮入 |
| 优化器刚停 | ❌ 无 | 🟡 30-120min | ❌ 未更新 | 🟡 需下次检查确认优化器是否真停了 |
| 双停 | ❌ 无 | 🔴 >2h | 🔴 天级未更新 | 🔴 全卡死 |
| 优化器结束后 Bot 恢复 | ✅ 有 | 🔴 >2h | ❌ 未更新 | 🟢 切换到 Bot 阶段 |

**关键观察：优化器处理完后不会自动通知看门狗或 Bot 管道。** 优化器只写 `multi-tier-opt/` 子目录，不写 `pipeline-progress.json`，不写 `auto-batch-request.json`。当优化器完成批量后，管道等待外部驱动/Agent 来读优化结果并启动下一阶段。这是两条独立链之间的自然断点。

---

### 19. Headless Batch-Mode Resumption — 批跑自主恢复与 Editor 无关的活性

> **2026-07-16 23:29 发现的新模式。** 管道在看门狗判定 `stuck=True`（Unity Editor 不存在、无 bot 目录 5 小时）后，**自主恢复**了批次产出——不是通过 Unity Editor 的 `PollForRequest` 循环，而是通过 `submit_batch_unity.py` 启动 headless Unity 实例。这揭示了批跑管道的一个关键特性：**活性可以完全独立于 Unity Editor 存在**。

**场景特征：**

| 信号 | 状态 | 含义 |
|------|------|------|
| `unity_editor_running` | ❌ **false** — 持久 Unity Editor 进程不存在 | 但这不是卡死信号（见 §3 关键区分）|
| 最近 30 分钟新 Bot 目录 | ✅ **有**（如 `L59_81-82_T2-{ts}-batch-range/` 含 CSV） | 真实数据产出 |
| Bot 目录格式 | `-batch-range` 子目录式（T1/T2 等） | 来自 `submit_batch_unity.py` 的 batch mode |
| `levels_done` | ❌ 仍冻结（9+ 天） | 评估/晋级链依然断裂 |
| `stuck_count` 历史 | 上次检查为 **≥1** | 看门狗曾判定为卡住 |
| Python batch runner 进程 | ✅ 存在（如 Hermes venv 下的 python） | 驱动 chain 的批跑侧活着 |

**实例（2026-07-16）：**
```
21:55 ─ stuck=True, stuck_count=1（或 2）
         unity_editor_running=false
         最新 bot 目录 16:57（5 小时前）
         30min 窗口内无活动
         → 看门狗判定为完全卡住

23:02~23:27 ─ 批跑自主恢复产出:
               L59-59 T1 (23:04)
               L59_81-82_89_91_98 T1 (23:16)
               L59_81-82_89_91_98 T2 (23:27, 含完整 CSV)
               Unity Editor 从未运行 → headless 实例产出
```

**与 §15（submit_batch 空转）的区别：**

| 维度 | Submit-Batch 空转 (§15) | Headless Batch-Mode Resumption (§19) |
|------|-----------------------|--------------------------------------|
| 产出了数据？ | ❌ 无 — Unity 不在，request 不被消费 | ✅ **有** — CSV 数据文件完整 |
| Unity 存在形式 | ❌ 不存在（submit_batch 在等却永远等不到） | ✅ **Headless 实例短暂运行**（`submit_batch_unity.py` 的子进程）|
| `auto-batch-request.json` | 存在且新鲜（不断生成） | 可能存在，也可能已被消费 |
| 看门狗判 stuck | `true`（请求不被消费） | `false`（有数据产出 = 有活性） |
| 是否需人工干预 | 是（启动 Unity Editor） | 否（批跑自主恢复了） |

**看门狗处理规则：**

1. **`unity_editor_running = false` 不是卡住信号**：当 `-batch-range` 目录存在且有 CSV 数据时，即使 Editor 不在，管道也处于**批跑自主活性**状态。看门狗应判 `stuck = false`，`stuck_count` 归零。

2. **`stuck_reason` 应注明恢复路径**：例如 `"batch-mode resumption after stall — headless Unity instances producing data. levels_done still frozen at 15 (9+ days), but bot runner active. Unity Editor not required for batch mode."`

3. **stuck_count 重置策略**：有新的 `-batch-range` 目录 → `stuck_count = 0`。这与 §18（Post-Stuck Retest Flurry）相同——机械活性恢复就归零，不管 levels_done 是否随动。

4. **警惕假阳性判卡住**：如果看门狗只看 `unity_editor_running` 作信号，会在 Editor 不存在时假判卡死。**正确做法：优先看 bot 目录活性（新 `-batch-range` 目录 + CSV 内容），其次看 Unity Editor 进程。** bot 目录是事实上的产出证据，Editor 进程只是辅助信号。

**与 §11 Mixed State 的关系：**

| 维度 | Mixed State (§11) | Headless Batch Resumption (§19) |
|------|------------------|--------------------------------|
| Unity 形态 | **Editor 持久进程** (GUI) | **Headless 实例** (短暂进程) |
| bot 目录来源 | PollForRequest 循环消费 | submit_batch_unity.py 独立产出 |
| 看门狗检测 | `ps -W \| grep Unity` 看到 Editor | `ps -W` 只看到短暂 headless 进程或无；依赖 bot 目录 CSV |
| 核心障碍 | 评估/晋级链断 | 评估/晋级链断（相同根本问题）|
| **下阶段演进** | 自动转为 Full Stall（无后续 request） | 也可转为 Full Stall（批跑完成后无下一批）|

> **实战演化路径（2026-07-16）：** 管道从 §17（Resume-Then-Die Cycle）→ §18（Post-Stuck Retest Flurry）→ §19（Headless Batch-Mode Resumption）的混合。Unity Editor 未曾在本会话中运行，但 `submit_batch_unity.py` 的 batch mode 自主恢复了活动。管道既不是死的也不是全活的——它是"机械层活着，评估层死了"的持续状态。

**检测脚本：**

```bash
# 检测 headless Unity 是否在近期产出了数据（不依赖 Editor 进程存在）
# 方法：检查最新 bot 目录是否含 CSV + 无持久 Unity Editor

# Step 1: 获取最新 bot 目录
LATEST_BOT=$(ls -t telemetry/bot/ | head -1)
echo "Latest bot dir: $LATEST_BOT"

# Step 2: 检查是否有 CSV 数据
CSV_COUNT=$(find "telemetry/bot/$LATEST_BOT" -name "*.csv" 2>/dev/null | wc -l)
echo "CSV files: $CSV_COUNT"

# Step 3: 检查目录名是否含 -batch-range（batch mode 产出）
IS_BATCH_MODE=$(echo "$LATEST_BOT" | grep -c '\-batch-range')
echo "Batch mode: $([ $IS_BATCH_MODE -eq 1 ] && echo 'yes' || echo 'no')"

# Step 4: 检查 Unity Editor 是否存在（排除 headless）
EDITOR_PID=$(ps -W | grep -i 'Unity\.exe' | grep -v Hub | grep -v Licensing | grep -v PackageManager | awk '{print $1}')
if [ -z "$EDITOR_PID" ]; then
    echo "Unity Editor: NOT running"
    echo "→ Assessing mode: headless batch resumption (if CSV data present)"
else
    # 进一步确认是否有 headless 参数
    CMD_LINE=$(wmic process where "processid='$EDITOR_PID'" get CommandLine 2>/dev/null | grep -v CommandLine)
    IS_HEADLESS=$(echo "$CMD_LINE" | grep -c '\-batchMode')
    if [ "$IS_HEADLESS" -eq 1 ]; then
        echo "Unity Editor: NOT running (headless batch instance only)"
    else
        echo "Unity Editor: RUNNING (GUI persistent process)"
    fi
fi
```

---

## 看门狗投递策略（Cron Job 告警抑制与升级）

> **问题：** 连续 N 次相同报告 → 用户被重复告警骚扰，看门狗失去有效性。
> **目标：** 第一次明确告知，第二次升级，第三次及以后静默直到状态变化。

### 连续卡住状态下的投递规则

| 连续卡住计数 | 投递行为 | 说明 |
|-------------|---------|------|
| 第 1 次检测到卡住 | ✅ 完整报告 + 🔴 大红色判定 | 首次出现问题，全面诊断 |
| 第 2 次连续卡住 | ✅ 简要报告 + 与上次对比 + ⚠️ 升级标记 | 确认问题不是偶发 |
| 第 3+ 次连续卡住 | **[SILENT]** | 状态未变，不再重复投递。直到 levels_done 或 bot 目录有新活动才恢复 |

> **⚠️ 渐进式确认规则（Mitigating Circumstances Exemption）**：当`stuck_count` 应从 0→1 时（即首次满足卡住条件），如果存在**可解释当前停滞的合理原因**（如 Unity 进程刚刚恢复运行、批次刚刚完整产出、当晚有连续的 T1→T5 活动但刚结束），看门狗应输出「⚠️ 临界状态」而非「🔴 首次卡住」，且 **不递增 stuck_count**。这在逻辑上等价于「暂缓判卡住并观察下次检查」。仅在第二次连续检查仍满足条件且无新进展时，才正式将 stuck_count 从 0→1。
>
> **实例（2026-07-10 01:36 检查）：** T5 批次刚于 00:38 完成，Unity.exe 首次被检测到运行中（此前检查 Unity 均未运行）。虽然 `levels_done` 未变且 30 分钟内无新 bot 目录，但 Unity 刚出现是合理的新阶段信号，看门狗输出「临界状态」并等待下次确认。02:08 时仍无变化，才正式判卡住。
>
> **判断是否需要暂缓的标准：**
> - ✅ **应暂缓**：Unity 进程在上次检查中不存在、本次新出现（说明管道可能刚进入处理阶段）
> - ✅ **应暂缓**：最近的完整批次（T1-T5）刚在 1 小时内完成，可能是批次间正常间隙
> - ✅ **应暂缓**：当天有 bot 活动且少于 2 小时未活动（burst 间歇期）
> - ❌ **不应暂缓**：Unity 进程一直存在、无任何新信号出现、停滞 >2 小时
> - ❌ **不应暂缓**：上次检查已是临界状态，本次仍无变化 → 必须确认卡住

### 实现方式

`pipeline-progress-check.json` 新增字段 `stuck_count`：

```json
{
  "stuck_count": 2,
  "last_stuck_alert": "2026-07-07 16:55"
}
```

**检查逻辑：**

```
if levels_done 变化 OR 有新 bot 目录 OR progress.json mtime 比 last_progress_update 新:
    reset stuck_count = 0
    输出完整报告（🟢 恢复）
elif stuck_count == 0:
    stuck_count = 1
    输出完整报告（🔴 首次卡住）
elif stuck_count == 1:
    stuck_count = 2
    输出简要升级报告（⚠️ 第二次卡住）
else:
    stuck_count += 1
    不输出报告 → [SILENT]
```

> ⚠️ **关键细节：** 恢复判定中，**progress.json 的 mtime 更新**是一个独立的活性信号，与 levels_done 是并列关系。即使 levels_done 没变，mtime 更新也说明有脚本在写进度——管道仍在工作。检查时应比较 `stat progress.json` 的 mtime 与 checkpoint 中的 `last_progress_update`。

**恢复判断优先级（一种即视为恢复）：**
1. `levels_done` 比 last_check 增加 → 推进了
2. 最近 30 分钟有新 bot 目录 → 有活动
3. `pipeline-progress.json` 的 `last_progress_update` 比上次检查新 → 有人改过

> **📌 关键细化：区分「30 分钟窗口活动」与「上次 cron 以来有活动」。** 看门狗可能每 15/30/60 分钟运行。`bot_active_30min=false` 不意味着自上次检查后完全无活动。当 `new_dirs_since_last_check >= 1`（上次检查以来有新目录）但 `bot_active_30min=false`（最近 30 分钟无）时，管道处于 **"近期有产出但当前静默"** 状态。看门狗应：
>   - 记录 `stuck=true`（当前无活跃进程）
>   - **不重置 stuck_count**（管道已进入静默期）
>   - 在 `stuck_reason` 中注明"自上次 cron 以来有 {N} 个新目录（最后 {X} 分钟前），但当前无活动"
>   - 按 stuck_count 规则正常递增（首次/二次卡住要报告，三次以上抑制）
>   - 避免将 stuck_count 重置为 0（因为那不是恢复，只是活动窗口恰好跨越了检查边界）

### ⚠️ 禁止无上限重复投递

看门狗 cron 可能每分钟、每 15 分钟或每 1 小时运行。如果每次运行都投递同样的 \"管道卡住\" 报告，用户会收到数十条重复通知。

**硬规则：** 当 `stuck_count >= 2`（即已投递过至少两次卡住告警）且除 `stuck_count` 外无其他字段变化时，必须 [SILENT]。

**例外（即使 stuck_count 高也要投递）：**
- `levels_done` 变了（哪怕只+1） → 恢复报告
- 新 bot 目录出现 → 恢复报告
- Unity 进程从运行变为消失 → 新异常，重新报告

---

## 综合判定规则

| levels_done 变化 | 30分钟内新 bot 目录 | auto-batch-request.json | Unity 状态 | 外部驱动进程 | monitor_bot.py | 结论 |
|---|---|---|---|---|---|---|---|
| 无 | 无 | 存在且陈旧（mtime 早于最新 bot 目录） | **已退出** | 无 | — | 🔴 **管道死亡（管道已死 — Dead）** — Unity 已退出，request.json 存在但从未被消费（mtime 早于最新 bot 目录或早于数小时）。`auto-batch-request.json` 里有待跑关卡但 Unity 不在所以不可能被消费。需先重启 Unity，删除残留 request，再重新提交。与 stale request（§4）的区别：stale request 可能发生在 Unity 还在运行但 TryDelete 失效时；dead 的特异性信号是 Unity 已退出 + request 存在 |
| 无 | 无 | 不存在 | 运行中 | 有（monitor_bot.py） | ⏳ 运行中 >5min | 🔴 **monitor false negative** — export 已写完但 monitor 启动太晚，永远等不到 mtime 变化。数据就绪，杀 monitor 后手动推进 |
| 无 | 无 | 不存在 | 运行中 | 有（其他） | — | 🟡 **刚刚完成** — bot 目录是最后批次残留，Unity 刚退出，无下一请求 |
| 有 | 有 | — | 运行中 | 有 | — | 🟢 **正常运行** |
| 无 | 无 | 存在 | 运行中 | 有 | — | 🟡 **批次运行中** — request 未消费，大概率在跑 |
| 无 | 有 | 不存在 | 运行中 | 有 | — | 🟢 **正常运行** — 驱动在写下一个 request |
| — | — | — | 不存在 | — | — | 🔴 **Unity 进程已退出** — 可能是崩溃 |
| 无 | 有（同关卡重复） | 不存在 | 运行中/已退出 | 无 | — | 🔴 **同关卡空转** — 无外部驱动，管道在同一关反复跑 |
| **无（14h+）** | **有** | **存在** | **运行中** | **有（monitor 在旧目录）** | — | 🟡 **长批次进行中** — levels_done 冻结 + 持续有新 bot 目录 + Unity 日志活跃。这是'数据收集模式'，不是卡住。但需确认 Unity 日志 mtime < 5min 以确认还在跑 |
| **无** | **有（新目录为空）** | **存在** | **运行中** | **有** | — | 🟢 **批次切换中** — 旧批次刚完成，新请求已提交，Unity 准备写入新目录 |
| **无** | **无（当天有 + CSV 完整）** | 不存在 | 运行中 | 无/有 | — | 🟡 **Burst 间歇期** — 当天有 bot 产出（含 CSV 数据），但当前处于批次间间隙。放宽时间窗至 2h 再判。不是真卡住，但需关注如果超过 2h 也无下一轮活动 |
| **无** | **无（T1–T5 齐全）** | **不存在** | **运行中** | **无** | — | 🔴 **Post-Batch Stall（Bot）** — 批次成功完成（T1–T5 齐全），外部驱动未提交下一请求。数据就绪未消费。详见 §9 |
| **无** | **无（opt 子目录全部完成）** | **不存在** | **不存在** | **无** | — | 🔴 **Post-Batch Stall（Optimizer）** — 优化器批次内所有关已全部完成（summary.csv 齐全），无任何进程在运行。优化器不自动触发下一阶段。详见 §14 |
| **无** | **有（`-batch-range` 目录 + CSV）** | 存在/不存在 | **不存在（Editor）/ 有（Headless）** | **有（submit_batch 或 Python batch runner）** | — | 🟢 **Batch-Mode 自主活性** — Unity Editor 未运行，但 headless Unity 通过 `submit_batch_unity.py` 产出了数据。这是 batch-mode 的正常行为，**不是卡住**。`stuck_count` 应归零。`stuck_reason` 注明"batch-mode resumption, levels_done still frozen" |

**扩展规则：`unity_editor_running = false` 时应检查更多信号再判 `stuck`：**
1. 最新 bot 目录是否含 `-batch-range` 后缀且内有 CSV 文件 → ✅ Headless batch-mode 活性，不计为卡住
2. 最新 bot 目录的 CSV winCount/failCount 是否非零 → ✅ 真实数据产出
3. Python 进程是否含 `submit_batch_unity.py` 或类似名称 → ✅ batch runner 活跃

---

## 建议处理动作

### 卡住时

1. 检查 Unity Editor.log 最后是否有异常（崩溃/编译报错/无限等待）
2. 检查 `grep "ExitCode:" BuildLogs/unity-launch-*.log` — ExitCode 3/4 = **编译错误**，非运行时崩溃。恢复步骤见 `blastgame-level-optimizer references/stall-recovery.md` → `## Unity 编译错误阻塞`。**不要重启 Unity — 编译错误重启解决不了。**
3. 检查 BuildLogs 下是否有 crash dump
4. 重启流程：
   - 确认 Unity 活着 → 手动注入 `auto-batch-request.json` 恢复流程
   - Unity 已死 → 启动 Unity，等待就绪后写入第一个 request
5. 如 `pipeline-progress.json` 明显落后于已实际完成的关卡，手动更新或触发驱动脚本补写

### 通知模板

```
⚠️ 管道可能卡住
进度: {levels_done}/{levels_total} 关完成 ({scope})
最后活动: {minutes_ago} 分钟前（{last_bot_dir}）
Unity 状态: {running/idle/crashed}
外部驱动: {running/stopped}
建议: {action}
```

---

## 已知坑

1. **`levels_done` 可能不是实时进度** — 如上所述，progress.json 可能数日不更新而批次仍在跑。以 bot 目录 mtime + auto-batch-result.json 为更实时的信号。
2. **`levels_done` 字段与 `done` 数组长度可能不一致** — 2026-07-06 实测：`levels_done: 8` 匹配 `done` 数组的 8 个元素，但之前检查曾误报为 9（人工计数或混入 `勉强`/`已优化` 关卡）。**始终数 `done` 数组长度**，不直接信任 `levels_done` 数值字段。
3. **没有外部驱动脚本 = 必然卡住** — 2026-07-06 三次连续检查（13:14、13:47、14:19）均证实：一旦 `auto-batch-request.json` 被消费，无外部脚本写入下一个，管道必然停留在当前关卡空转。这是**确认的规律**，不是偶发。
4. **Bot 目录活动可能短暂超出 Unity 生命期** — Unity 退出前的最后批次仍会写入 bot 目录，导致出现 "Unity 已死但 bot 目录在 30 分钟内" 的窗口期。此时看门狗应标记为 "刚刚完成" 而非 "正常运行"。
5. **`pipeline-progress-check.json` 作为历史记录** — 该文件记录上次检查快照，初次运行或无此文件时无法做 delta 判断（`levels_done` 变化比较），只能基于 bot 目录和 request 文件状态做单项判断。
   - **`session_search` 降级方案（Hermes 平台技巧）**：当 checkpoint 文件不存在时，用 `session_search(query="pipeline-progress levels_done", sort="newest", limit=3)` 检索最近 cron 会话的输出，从中提取先前报告的 `levels_done` 值作为基线。从搜索结果的 `bookend_end` 字段（通常含最终状态摘要如 `levels_done=15`）或 `messages` 中的工具调用参数可发现前次读取的数值。注意：`session_search` 只返回会话快照（±5 条消息 + 书结尾），不是完整日志；如果之前会话因错误未能完成或输出被截断，搜索结果可能缺失所需数值。此方案仅作为 read_file checkpoint 失败的备用，不替代 checkpoint 主方案。
6. **进程名冲突** — `tasklist` 输出的 Unity 进程可能是其它 Unity 项目，需确认 projectPath 匹配。通过 `unity-launch-v{N}.log`（或 `-test{N}.log`）的启动参数确认。
7. **Hermes python 进程干扰** — `tasklist | grep python` 会显示多个 Hermes 后台进程，需用 `wmic` 或 `ps aux` 区分是否为管道驱动脚本。
8. **pipeline-progress.json 的手动修改** — 如果人工介入调整进度，levels_done 可能跳变，看门狗应容忍非递减变化（如 9→12 或 9→10），但 9→9 可能为正常（处理中的关卡还未标记完成）。
9. **`monitor_bot.py` false negative（永久等待）** — monitor_bot.py 进程存活 + `auto-batch-last-export.txt` 和 `auto-batch-result.json` 存在且内容完整 + 无新 bot 目录 + Unity 运行中 = monitor 启动太晚错过了信号。检查方法：对比 `auto-batch-last-export.txt` 的 mtime 与 monitor 进程启动时间（`ps -p <pid> -o lstart` 或 `stat /proc/<pid>/`）。如 export mtime 早于 monitor 启动时间 → 已中 false negative。恢复：杀 monitor 进程，直接读 result.json 的 export 路径取数据，手动推进 pipeline。
10. **`pipeline-progress-check.json` 的 `done_array_count` 自检** — 2026-07-08 检测发现 `levels_done=15` 可以与 `done` 数组长度交叉验证（均应为 15）。推荐每次检查记录 `done_array_count` 字段，不一致时预警 JSON 可能损坏或手动修改过。详见 `references/checkpoint-schema.md`。
- **`unity_editor_running = false` 不等于管道死亡** — 如果不在 Editor 模式下运行（batch-mode headless Unity），bot 目录依然可以正常产出。看门狗必须分开检查 Unity Editor 进程和 headless 实例。详见 §3「关键区分」和 §19。

---

### 20. Partial Batch Completion — 批次部分完成，最后档位缺失

> **2026-07-17 实测发现的模式。** Batch-mode 成功运行了大部分 tiers（T1-T4），生成了完整的 CSV 数据，但最后一个 tier（T5）**从未出现过**，且 Unity 进程已退出。不同于 §3 的 T-子集跳过模式（中间档位被故意跳过），缺失的档位是最后一位且不是故意的。

**信号集：**

| 信号 | 状态 | 含义 |
|------|------|------|
| `-batch-range` 目录存在 | ✅ 有 | batch mode 确实运行过 |
| T1…T(N-1) 子目录 | ✅ 完整（含 `campaign-attempts-*.csv` 和 `campaign-summary-*.csv`） | 已完成档位产出了真实数据 |
| **最后 tier T(N) 子目录** | ❌ **不存在**（无对应目录） | 批次在完成最后一个 tier 前停止了 |
| 缺失位置 | **末尾**（不是中间） | 区别 T-子集跳过模式（§3 批量格式） |
| Unity.exe | ❌ 已退出 | headless 进程已完成或崩溃后退出 |
| `auto-batch-request.json` | 不存在（已被消费）或残留 | 请求已被消费，但未触发下一批次 |

**实例（2026-07-17）：** 批次 `82_89-91_98` 配置为 `--tiers 1,2,3,4,5`（5档），实际产出了 T1(11:52)、T2(11:56)、T3(12:07)、T4(12:18) 各含完整 CSV，但 T5 目录不存在且 Unity.exe 已退出。

**检测方法：**

```bash
# 最新 bot 目录
LATEST=$(ls -t telemetry/bot/ | head -1)
echo "Batch dir: $LATEST"

# 列出该目录下的 T 子目录（应命名如 L82_89-91_98-T1-...）
ls -d "$LATEST"/*T[1-5]* 2>/dev/null | sed 's/.*T/T/' | sort

# 如果 T5 不存在但 T1-T4 都在 → Partial Batch Completion
```

**看门狗处理：**

- `stuck = true`（批次未完成，Unity 已退出）
- `stuck_reason` 应注明：`"partial batch completion — T1-T{N-1} done with CSV, T{N} never appeared, Unity exited"`
- `stuck_count` 按标准规则递增
- 恢复路径：检查 Unity crash 日志 → 重启 Unity → 重新提交该批次（至少补跑缺失的最后一档）

**与相似模式的区别：**

| 模式 | 缺失位置 | Unity 状态 | CSV 数据 | 含义 |
|------|---------|-----------|---------|------|
| §3 T-子集跳过 | **中间**（如缺 T2,T4） | 可能仍在运行 | 齐全 | **故意跳过** — 验证轮次，节省时间 |
| §20 Partial Completion | **末尾**（如缺 T5） | ❌ 已退出 | T1-T(N-1) 齐全 | **非故意** — batch 在完成前终止 |
| §15 submit_batch 空转 | 无目录产出 | ❌ 不存在 | 无 | Unity 从未运行，request 不被消费 |
| §4 Bot 死在导出阶段 | 整个目录不存在或为空 | ❌ 不存在/崩溃 | 无 | 批次在 WriteResult 阶段被中断 |

**可能根因（需排查）：**
1. Unity headless 实例在加载 T5 配置前崩溃 — 检查 Unity 日志中是否有 `ExitCode:` 或崩溃信息
2. T5 被配置为特别长的运行（如更多 runCount），尚未完成时用户/系统关闭了 Unity
3. script/unexpected `-quit` 参数 — `submit_batch_unity.py` 可能在 T4 完成后触发了 `-quit` 退出
4. 系统资源耗尽（OOM）— T5 即将开始时内存不足，Unity 被系统杀死

---

## 14. Optimizer Post-Batch Stall — 优化器完成批次后无下一请求

> 2026-07-12 实测发现的新模式。优化器（multi-tier-opt）完成其批次内所有关卡的处理后，管道进入全停滞状态，因为优化器本身不触发下一阶段。

**信号集：**

| 信号 | 状态 | 含义 |
|------|------|------|
| `multi-tier-opt/` 最新子目录 ctime | < 30 分钟前 ✅ | 优化器刚刚有过活动 |
| `multi-tier-opt/` 最新关的子目录内文件 | 全部阶段齐全（phase0→1→2→sensitivity→summary→detail） | 该关已彻底完成 |
| 优化器当前批次所有关 | 全部完成（如 `51✅ 54✅ ... 98✅`） | 批次内无剩余关卡可处理 |
| 30 分钟内新 Bot 目录 | ❌ 无 | Bot 管道未参与 |
| Unity 进程 | ❌ 不存在 | Unity Editor 未运行 |
| Python/Hermes 驱动进程 | ❌ 不存在 | 无外部驱动写下一请求 |
| `levels_done` | ❌ 冻结（多日未变） | 优化器不更新此值 |
| `pipeline-progress.json` mtime | ❌ 天级未更新 | 评估链未接入优化结果 |
| `auto-batch-request.json` | 不存在 | 无待消费的 Bot 请求 |

**实例（2026-07-12 09:56）：**

```text
07-11 14:22 ─ 优化器批次开始（L51~98 共 15 关）
07-11 14:22~07-12 09:35 ─ 逐关处理，平均 ~1.5h/关
07-12 09:35 ─ L98 完成：summary.csv + detail.csv + sensitivity.csv 全部写入
07-12 09:35 ─ 优化器停止，无任何后续进程
07-12 09:56 ─ 看门狗检测：levels_done=15 (冻结 5d)、无 bot 目录、无 Unity、无 Python
              → stuck=True, stuck_count=1 (Optimizer Post-Batch Stall)
```

**与 §9（Bot Post-Batch Stall）的区别：**

| 维度 | Bot Post-Batch Stall (§9) | Optimizer Post-Batch Stall (§14) |
|------|--------------------------|----------------------------------|
| 最后活跃组件 | Unity Editor (BlastBotAutoBatchTrigger) | multi-tier-opt 优化器进程 |
| 产出物 | `telemetry/bot/` 下的 CSV 目录 | `telemetry/multi-tier-opt/` 下的 phase/summary CSVs |
| Unity 进程 | 可能仍在运行（空闲等待） | 不存在（优化器不需要 Unity） |
| `auto-batch-request.json` | 不存在（已被消费） | 不存在（从未涉及 Bot 阶段） |
| 数据就绪 | Bot 实测数据已产出，未被 ingestion 消费 | 优化器推荐配置已产出，未被下一阶段消费 |
| 恢复方向 | 提交下一 Bot 请求 或 人工评估结果 | 读 optimizer summary → 提交 Bot 验证请求 或 启动下一优化批次 |

**恢复步骤：**

1. **确认优化器批次确已全部完成：** 检查当前批次下所有关的子目录是否都有 `summary.csv`。例如 `find "multi-tier-opt/{batch_name}/" -name "summary.csv"` 计数应等于批次包含的关卡数
2. **读取优化器摘要：** 最新批次的 `summary-{batch_name}.csv`（顶层目录下的全局汇总）包含各关各档位推荐配置和预期 WR
3. **提交下一批次请求：** 读取 `pipeline-progress.json` 的 `pending` 数组，找出未处理的关卡，提交新的 optimizer request
4. **或切换到 Bot 验证阶段：** 如果优化结果需要 Bot 实测验证，写 `auto-batch-request.json` 启动 Unity Bot 批跑
5. **更新进度文件：** 可选地将优化器完成的关卡状态从 `"ggk"`（改关卡）推进为可验证状态，为后续 Bot 验证做准备

**看门狗处理规则：**

| 场景 | Opt 30min 内 | Opt 批次状态 | 30min 新 bot 目录 | Unity | 判定 |
|------|-------------|-------------|-----------------|-------|------|
| 优化器正在处理 | ✅ 有 | 仍有未完成关 | ❌ | ❌ | `stuck=false`（正常优化中） |
| 优化器刚完成全批次 | ✅ 有（<30min） | **全部完成** | ❌ | ❌ | `stuck=true`（**首次卡住**—Optimizer Post-Batch Stall。完成即刻判卡，不等 2 次确认，因为完成信号本身是明确的事后标记） |
| 优化器完成已>30min 无后续 | ❌ 无 | 全部完成 | ❌ | ❌ | `stuck=true`（确认停滞。如果 stuck_count 已≥2 且无其他变化 → [SILENT]） |
| 优化器完成 + Bot 阶段开始 | ❌ 无 | 全部完成 | ✅ 有 | ✅ | `stuck=false`（切换成功，Bot 阶段恢复） |

**⚠️ 特殊 stuck_count 处理：** 当优化器从活跃→刚完成时（§14 判定为首次卡住），`stuck_count` 应从 0→1 但不受限于 §「渐进式确认规则」的暂缓要求——因为这里的"卡住"不是活性未知的暂缓场景，而是批次完成的事后确认，信号明确。在 stuck_count 已≥1 的情况下，后续检查如果没有新优化器活动且无 Bot 恢复，按标准抑制规则执行（≥3 次后 [SILENT]）。

---

## 15. submit_batch.py 活跃但 Unity 未运行（空转 Stall）

> **2026-07-14 实测发现的模式。** 与 §9/§10 不同：batch-runner 已完成其工作但 `submit_batch.py` 进程仍在运行，不断写入 `auto-batch-request.json`，而 Unity Editor 不存在（崩溃或从未启动）。

**场景特征：**

| 信号 | 状态 | 含义 |
|------|------|------|
| `levels_done` | ❌ 冻结多日 | 评估/晋级链断裂 |
| 最近 30 分钟新 Bot 目录 | ❌ 无 | Unity 不在，无批次产出 |
| **`auto-batch-request.json`** | ✅ **存在且 mtime 新鲜**（最近 30 分钟内有覆写） | submit_batch 循环在运作 |
| auto-batch-request 内容 | level 不同于最新 Bot 目录，是新的一批 | 不是 stale request（§4），是**新的待消费请求** |
| **`ps -W \| grep submit_batch`** | ✅ **有匹配进程** | submit_batch.py 正在运行 |
| Unity 进程 (`ps -W \| grep Unity.exe`) | ❌ 不存在 | 编辑器崩溃或未启动 |

**检测方法：**

```bash
# 1. 查找 submit_batch.py 进程
ps -W | grep submit_batch
# 或更详细
wmic process where "commandline like '%submit_batch%'" get ProcessId,CreationDate,CommandLine

# 2. 确认 request 是否新鲜（非 stale）
ls -la BuildLogs/auto-batch-request.json
stat -c '%y' BuildLogs/auto-batch-request.json       # mtime 应接近当前时间
cat BuildLogs/auto-batch-request.json                 # 检查 levelSpec

# 3. 确认 Unity 不存在
ps -W | grep -iE '(Unity.exe$)' | grep -v Hub | grep -v Licensing

# 4. 检查 submit_batch 时间是否与 request mtime 吻合
#    submit_batch.py 启动后先写 request，再等待消费
#    如果 request mtime 与 submit_batch 启动时间（CreationDate）接近 → 是同一个循环
```

**典型输出（2026-07-14 17:47 实例）：**

```bash
# ps -W | grep submit_batch
#   PID  ...
#   python3...submit_batch.py 93 --skip-patch --tiers=1 --games=400 --force  (15:38)
#   python3...submit_batch.py 80 --skip-patch --tiers=2,3 --games=400 --force  (17:31)

# ls -la BuildLogs/auto-batch-request.json
#   -rw-r--r-- 1 Administ 123 2026-07-14 17:40

# cat BuildLogs/auto-batch-request.json
#   {"levelSpec": "80", "runCount": 400, "levelFolder": "test",
#    "tiersCsv": "2,3", "recordReplay": false, "tag": "batch-80-80"}
```

**submit_batch.py 生命周期（2026-07-14 实测）：**

```
submit_batch.py L{N} 启动
  → 写 auto-batch-request.json（QueueRequest）
  → 生成 trigger_{ts}.cs 触发 Unity 编译
  → wait_consumption(600s)           ← 轮询 request 是否被删除（消费）
  → ❌ 600s 超时（Unity 未消费）
  → 继续等 auto-batch-result.json    ← 轮询结果文件（最长 7200s）
  → ❌ timeout 超时
  → 写 BuildLogs/_stall.json         ← 记录 stall
  → exit(2)                          ← 退出
  ─────────────────────────────────────
  → 外部调度器/Hermes 可能立即启动新的 submit_batch（另一关卡）
  → 重复以上过程
```

**与 §4 Stale Request 的关键区别：**

| 特征 | Stale Request (§4) | Submit-Batch 空转 (§15) |
|------|-------------------|------------------------|
| request.json mtime | 旧（早于最新 bot 目录） | **新鲜**（等于 submit_batch 启动时间附近） |
| request.json 的 levelSpec | 与已完成 bot 目录同关卡 | **新的关卡、新的 tier/局数配置** |
| `ps -W \| grep submit_batch` | 无 | ✅ 有（进程活跃） |
| auto-batch-last-export.txt | 指向已完成的旧批次 | 指向已完成的旧批次或无内容 |
| 本质 | Unity TryDelete 环节失效后的残留 | submit_batch 循环在空跑，不断生成新请求 |

**根因：** Unity Editor 进程已退出（崩溃、被关闭、AutoQuitter），而负责写入 `auto-batch-request.json` 的外部驱动（Hermes 调度器、上一轮 cron 任务遗留的 submit_batch 进程）仍在运行。两条链完全断开：请求不断生成但永远不被消费。

**看门狗处理：**
1. 检测 Unity 进程不存在 → `unity_editor_running = false`
2. 检测 `ps -W | grep submit_batch` → `submit_batch_active = true`
3. 检测 `auto-batch-request.json` mtime → 如果最近 30 分钟内有新写入，说明 submit_batch 循环仍在运作
4. 判定：`stuck = true`
5. `stuck_reason` 应注明：`"submit_batch 活跃（L{X} @ {time}）但 Unity 进程不存在 — 请求不被消费"`
6. `stuck_count` 按标准规则递增（与 §9/§10 相同，不适用渐进式确认，因为 Unity 不在的状态明确）

**恢复方法：**
1. 手动启动 Unity Editor（BlastGame 项目）
2. submit_batch.py 的 `wait_consumption` 会在 1s 轮询中自动检测到 request 被消费
3. 或者：终止所有 submit_batch 进程 → 启动 Unity → 手动写 `auto-batch-request.json`

### 15.1 Submit-Batch 已退出但产出了数据（Stall After Output）

> **2026-07-14 实测变体。** submit_batch.py 在 Unity 缺席的情况下仍然完成了完整的生命周期（写 request → 等消费 → 超时 → 写 `_stall.json` → exit），且因其他机制产生了真实 Bot 数据。之后 submit_batch 已退出，留下 stall 记录和数据目录。

**与 §15 的关系：**
- §15：submit_batch 仍在运行，不断写 request 但 Unity 不消费
- §15.1：submit_batch 已走完生命周期退出，stall.json 已写入，数据已产出但 levels_done 仍未更新

**演进路径：**
```
§15: submit_batch.py 运行中（不断写 request, 等消费, 超时循环）
  → 某种因素产出 Bot 数据目录（如遗留的 Unity 批次机制）
  → submit_batch 完成超时循环, 写 _stall.json, exit
  → §15.1: 数据已产出, submit_batch 已退出, Unity 仍不存在
```

**看门狗识别：** `submit_batch_active = false` + `_stall.json` 新鲜 + `new_dirs_since_last_check >= 1` + `unity_editor_running = false` → `stuck = true`。stuck_count 按标准规则递增。报告中应注明"自上次 cron 以来有数据产出"作为积极信号，但不视为恢复（当前无活跃组件）。

---

### 16. Retest-Only Loop — 管道在已有关卡上空转，从不推进到 pending 关

> **2026-07-15 跨会话观察：** Retest-Only Loop 可反复发生——管道每天恢复几小时（重跑一批已有关卡），然后再次死亡，形成**间歇性 resume-then-die 循环**（见 §17 The Resume-Then-Die Cycle）。

**场景特征：**

> **2026-07-15 实测发现的模式。** 与 §11 Mixed State（Bot 产出数据但评估链断裂）类似，但更具体：管道**有选择地**只对已标记为 `done` 或 `ggk`（改关卡）的关卡执行 retest 批跑，从未对 `pending` 列表中等待推进的关卡（如 89, 90, 91, 95, 99, 100）提交任何请求。

**场景特征：**

| 信号 | 状态 | 含义 |
|------|------|------|
| `levels_done` | 冻结多日（8天+） | 无新关卡完成晋级 |
| 最近 30 分钟新 Bot 目录 | 有（但指向**已有关卡**） | Bot 在跑，但只跑已有结果的重测 |
| Bot 目录关卡名 | 全部是 `done` 或 `ggk` 中的关（如 L53, L54, L56, L57, L59） | pipeline 未触及 pending 关卡 |
| `pipeline-progress.json` 的 `pending` 数组 | 仍有未处理的关（如 89, 90, 91, 95, 99, 100） | **待推进关卡从未被消费** |
| `auto-batch-request.json` 内容 | 同样指向已有关卡或过时请求 | 从未包含 pending 关 |
| `pipeline-status.txt` mtime | 旧（多天前），内容与实际脱节 | 状态文件未同步 |
| Unity 进程 | 运行中 | 引擎正常，在等待或执行 retest |

**实例（2026-07-15 11:56）：**
- `levels_done=15` 自 07-07 起冻结 8 天
- 当天 Bot 目录：`L53_56-57_59`、`L54-54` — 全部是已标记 `done` 或 `ggk` 的关卡
- `pending` 数组仍有 6 关（89, 90, 91, 95, 99, 100）——从未被提交过
- `auto-batch-request.json` 自 04:17 起为 L71,76,78,84（同为 ggk 关，不是 pending 关），7.5h 未消费
- Unity 运行中（PID 85008）
- `new_dirs_since_last_check = 6` 但全是 retest

**实例 B（2026-07-16 10:41 — Full T1-T5 Retest 变体）：** 不同于 T-子集验证轮次（只跑 T1/T3/T5），管道对单一已有关卡 **L81** 在同一天内执行了 **两轮完整的全 5 档 (T1–T5) retest**（10:05 和 10:27 各一轮）。每轮都产出了完整的 campaign-summary CSV（322/400=80.5% win rate on T5）。`auto-batch-result.json` **根本不存在**（不是 stale，而是从未有过 result 文件）。`levels_done=15` 已冻结 9 天。Unity 进程运行正常，但评估/晋级链从未初始化。

| 维度 | 批次验证轮次（已有记录） | Full T1-T5 Retest（新观察） |
|------|----------------------|--------------------------|
| 档位覆盖 | 子集（如 T1/T3/T5 或 T2/T3） | **全部 5 档齐全** |
| 同一关卡重复次数 | 通常 1 次 | **可多次**（如 L81 在 22 分钟内跑了两次全 5 档） |
| 时间消耗 | ~8-12 分钟/轮（仅 2-3 tier） | ~22-25 分钟/轮 × 重复次数 |
| `auto-batch-result.json` | 可能存在（stale） | **完全不存**在（从未写过） |
| 含义 | Optimizer 快速验证改关卡配置 | 更深的 retest 模式——可能 optimizer 每次生成新全配置都要求完整验证，或 submit_batch 的请求没被 Unity 以正常方式消费+写回 |

**`auto-batch-result.json 从不存在的含义`**：当该文件完全不存在时，说明自上次系统重置/重启以来，评估链（ingestion）从未成功完成过一次数据回流。这是比 stale result (§4) 更强的信号——stale 至少说明过去有成功回流，从不存在的 result 说明 ingestion 链在本次 Unity 会话中从未建立。看门狗应记录 `result_json_ever_existed: false` 并在 stuck_reason 注明。此状态下即使 bot 目录有数据，pipeline 也无法自动推进，因为写入 result.json 是 TryDelete 前置条件——result.json 不存在意味着 AutoBatchTrigger 的 `WriteResult → TryDelete` 链条的起点就断了。

**检测方法：**

```bash
# 1. 获取最近 bot 目录的关卡前缀
ls -lt telemetry/bot/ | head -10 | grep -oP 'L?\d+[_\-]?\d*' | head -5

# 2. 对比 progress.json 的 pending 列表
cat BuildLogs/pipeline-progress.json | grep -oP '"pending":\s*\[[^\]]+\]'

# 3. 检查 auto-batch-request 内容是否涉及 pending 关
cat BuildLogs/auto-batch-request.json 2>/dev/null

# 4. 交叉验证：request 的 levelSpec 是否包含 pending 关
#    如果 request 的 levelSpec 从未包含 pending 关 → 确认 Retest-Only Loop
```

**根因推测：**
- Pipeline 的 request 生成逻辑（Hermes agent / batch-runner.py）可能在某种条件下退化为"重跑上次成功的请求"或"重跑已标记的改关卡"而不是推进到下一个 pending 关
- 或者 pipeline 在循环执行一个**固定的关卡子集**（如 L51-70 范围），忽略了 L71-100 的 pending 关
- 或者 `pending` 数组与 `levels_done` / `ggk` 之间存在边界重叠问题，agent 认为 pending 关已被其他状态覆盖

**与 §11 Mixed State 的区别：**

| 维度 | Retest-Only Loop (§16) | Mixed State (§11) |
|------|----------------------|-------------------|
| Bot 目录关卡选择 | 选定已有关卡，**从未涉及 pending** | 可能涉及新关也可能不涉及 |
| pending 列表状态 | 从未被消费（**持久冻结**） | 可能被消费过但无推进 |
| `auto-batch-request` 内容 | 重复提交已有关卡或 ggk 关 | 可能存在等待消费的新关请求 |
| 根本问题 | request 生成逻辑跳过 pending 关 | 评估/晋级链断裂 |
| 恢复路径 | **修改 request 生成逻辑**，重新提交 pending 关 | 读最新数据 → 判定 → 更新 progress |

看门狗处理：

1. `stuck = true`（当前无有效推进）
2. `stuck_reason` 应注明：`"retest-only loop — bot active on done/ggk levels only, pending={pending_list} never touched"`
3. `stuck_count` 按标准规则递增。**不适用渐进式确认规则**：即使 Unity 在运行、Bot 有产出，但没有推进到 pending 关的状态是明确的——重复 retest 不是正常的批次间间隙

**恢复方法：**
1. 手动检查 `pipeline-progress.json` 的 `pending` 数组
2. 提交新请求指向 pending 关（写 `auto-batch-request.json`），示例：`{"levelSpec":"89,90,91,95,99,100","runCount":400,"levelFolder":"test","tiersCsv":"1,2,3,4,5","recordReplay":false,"tag":"batch-pending-catchup"}`
3. 等待 Unity 消费并产出数据
4. 评估结果后更新 progress.json

---

### 17. The Resume-Then-Die Cycle — 间歇性恢复后再次死亡

---

### 18. Post-Stuck Retest Flurry — 卡住解除后只跑改关卡、不推进度

> **2026-07-16 实测发现的模式。** 管道在长时间卡住（stuck_count≥5，连续数小时无活动）后，因 Unity Editor 手动重启而恢复运行，但只产出针对已标记 ggk（改关卡）的批次目录，没有任何关卡从 ggk 晋升为 done。`levels_done` 在恢复后仍然冻结。这不同于 §16（持续跑改关卡），也不同于 §17（跨会话的反复死亡-恢复循环）。

**场景特征：**

| 信号 | 状态 | 含义 |
|------|------|------|
| `stuck_count` 历史 | 前次检查为 **≥3+ 连续卡住**（已进入 [SILENT] 抑制阶段） | 管道确实曾长时间停滞 |
| Unity 进程 | 本周期内 **新启动**（mtime 早于本检查的几分钟内） | 人工/外部干预启动了 Unity |
| 最近 30 分钟新 Bot 目录 | ✅ **有**（通常是暴发式：15 分钟内连续 2-3 个目录） | 管道机械活性已恢复 |
| 30 分钟窗口外但当天内目录 | ✅ 多个（如 6 个目录在 1h23m 内出现） | 恢复后有一段持续活动 |
| **Bot 目录关卡名** | 全部为 **ggk**（改关卡）中的关卡，无任何 `done` 或 `pending` 涉及 | 只跑已标记需要改的关 |
| `levels_done` | 🔴 **与卡住前完全一致，未增长（可能已冻结 9+ 天）** | 无任何关从 ggk 晋升到 done |
| `pipeline-progress.json` mtime | 🔴 天级未更新 | ingestion/评估链未介入 |

**实例（2026-07-16 16:38 检查）：**

```text
14:55 ─ stuck=true, stuck_count=5 (连续第5次)
        (最后目录 12:15, 160 分钟无活动)
        原因: Unity crashed earlier; Unity just restarted at 14:53

15:02~16:18 ─ Bot 暴发: 6 个新目录
               L82_89_91_98 → L82_89_91 → L82_89_91 → L82_89 → L89
               全部为 ggk 关卡
               间隔 ~15-25 分钟（正常批跑节奏）

16:38 ─ stuck=false (管道已恢复机械活动)
        但 levels_done=15 (与 14:55 一致，冻结 9 天)
        无任何 "done" 晋升
```

**看门狗处理规则：**

1. **关键判断：stuck=false 但 levels_done_changed=false。** 最核心的区别——看门狗应判定 **机械活性已恢复**（bot 有目录），但标注 **进度未恢复**（levels_done 未变）。

2. **stuck_count 重置策略：**
   - ✅ **立即 reset stuck_count=0** —— 机械活性已恢复（有新 bot 目录），不再处于"卡住"状态
   - ⚠️ 但 `stuck_reason` 应注明：`"levels_done frozen, post-stuck retest flurry on ggk levels"`
   - ❌ **不要保持 stuck_count 非 0** —— 否则下次检查时如果 bot 再次停摆且 levels_done 未变，stuck_count≥3 会直接 [SILENT]，漏报第二次卡住

3. **自动降级规则：** 如果连续 3+ 次检查（同一恢复期内）都检测到 bot 目录但 levels_done 未变，看门狗应在 stuck_reason 中标注 `"confirmed retest-only: {N} consecutive checks with bot activity but no done progression"`。这不改变 stuck 判定（保持 false），但为人工提供线索。

4. **`stuck_reason` 模板：**
   ```
   "Post-stuck retest flurry — pipeline mechanically recovered after Unity restart at {restart_time}, bot producing dirs on ggk levels {levels_list}. But levels_done remains frozen at {n} (unchanged since {date}). No ggk→done graduation observed."
   ```

5. **报告投递策略：**
   - 首次检测到 Post-Stuck Retest Flurry（即 stuck→unstuck 状态变化） → ✅ 完整恢复报告（🟢）
   - 后续集中检查（stuck=false 保持不变） → [SILENT]
   - 再次卡住（bot 目录停止 + levels_done 未变 + Unity 退出） → 作为新卡住事件从 stuck_count=0→1 开始报告

> **2026-07-15 实测发现的模式。** 管道在卡住报告后**短暂恢复**（跑几批合成批次、产出 Bot 数据），然后再次进入停滞——形成"恢复→死亡"的间歇性循环。这不是一次性的 Post-Batch Stall，而是反复的胶着状态。

**信号集：**

| 信号 | 状态 | 含义 |
|------|------|------|
| `levels_done` | 🔴 冻结多日（8天+） | 始终未推进 |
| 当天 Bot 目录（查看横跨 2+ 会话） | ✅ 有，但全部是**已有关卡的重跑** | 管道间歇性恢复 |
| 两次 stuck 报告间的新 Bot 目录数 | >0（如 Jul 14: 91→Jul 15: 121，+30 dirs） | 确已恢复过 |
| 但最近 30 分钟 | ❌ 无新目录 | 又进入停滞 |
| Unity 进程 | 从运行→退出（跨会话变化） | 恢复期内短暂运行后退出 |
| `auto-batch-request.json` | 存在且 stale（mtime 早于最新 bot 目录数小时） | 最后一轮请求未被消费 |
| `stuck_count` | 第 3+ 次连续检测到卡住 | 管道的胶着状态已固化 |

**实例（2026-07-14→15 跨会话）：**

```
2026-07-14 06:38 — stuck=true (stuck_count=1), Unity 运行中, 最后目录 01:37
2026-07-14 07:12 — stuck=true (stuck_count=2), 同上
           ⤵ [SILENT] — 第 3+ 次连续卡住，按抑制规则静默
2026-07-14 18:13~18:45 — 管道恢复: L80 T2-T4 再次运行 (+6 dirs)
2026-07-14 18:45~2026-07-15 02:27 — 再次静默
2026-07-15 02:27~10:26 — 大规模活动爆发: L53-100 单关 + L53 batch + L54 batch
                           Bot 目录数 91→121 (+30 目录)
2026-07-15 10:26 — 最后一次 batch 完成 (L54-54 T5)
2026-07-15 15:16 — stuck=true, Unity 仍在运行
2026-07-15 15:49 — stuck=true (恶化), Unity 已退出
           ⤵ 停滞: request.json (L71,76,78,84) 从 04:17 未被消费
```

**根因链条：**

```
Hermes cron 或其他外部驱动偶尔触发 request 提交
  → Unity 消费并产出一批 Bot 目录（~22-25min/tier）
  → 批次完成，TryDelete 写入 pipeline-status.txt
  → 评估/晋级链断裂，levels_done 不更新
  → 无后续 request 生成
  → Unity 空闲等待 → AutoQuitter 或用户关闭 Unity
  → 管道完全停止
  → 数小时后外部驱动再次触发 → 循环重复
```

**与 §9 Post-Batch Stall 的关系：**

| 维度 | Post-Batch Stall (§9) | Resume-Then-Die (§17) |
|------|----------------------|----------------------|
| 恢复次数 | **单次** — 批次完成后永久停滞 | **多次** — 间歇性恢复又死去，形成循环 |
| `stuck_count` 历史 | 从 0→N（单一停滞期） | 多次归零又增长（恢复→停滞→恢复→停滞） |
| `checkpoint` 趋势 | levels_done 持续冻结 | levels_done 冻结 + bot 目录计数跳跃式增长 |
| 最终状态 | 需要一次人工恢复 | **胶着状态** — 自动恢复只能短暂工作，根本问题是驱动链未修复 |
| 识别方法 | 跨天检查 bot 目录计数 | 跨天检查 bot 目录计数 + 对比 stuck_count 归零历史 |

**看门狗处理：**

当检测到 Resume-Then-Die 循环时（即 stuck_count 被 reset 过但 levels_done 始终未增长）：

1. **首次识别（跨会话检测）**：比较当前 `total_bot_dirs` 与文件中记录的 `prev_check_total_bot_dirs`。如果 `total_bot_dirs > prev_check_total_bot_dirs` 但 `levels_done` 未变，且 stuck_count 在此前曾被 reset 过 → 管道进入了 Resume-Then-Die 循环
2. **stuck_reason 应注明**：`"resume-then-die cycle — bot dirs grew from {prev} to {curr} but levels_done frozen; pipeline briefly recovers then dies again. root cause: evaluation chain broken, not single stall event."`
3. **stuck_count 抑制规则升级**：当确认为 Resume-Then-Die 循环后，即使后续检查发现 bot 目录计数增长，只要：(a) levels_done 未变，且 (b) 最近 30 分钟无新目录 → **不作恢复（不 reset stuck_count）**。因为 bot 目录增长只是恢复期的滞后产物，不等于管道已脱离停滞。遵循"levels_done 变才恢复"的严格标准。
4. **投递策略**：首次识别 Resume-Then-Die 循环时投递一次特殊报告（标记为 🟣 Purple，意为"胶着状态"），然后再次 [SILENT] 直到根本状态变化。

**报告模板（🟣 胶着状态）：**

```
🟣 管道陷入 Resume-Then-Die 循环

管道的自动恢复只能短暂工作（产出一批 Bot 数据），
然后再次死亡。这是一个反复的胶着状态。

levels_done: 15/50（8+ 天未增长）
Bot 目录增长: {prev} → {curr}（+{diff} 目录）
但 levels_done 未对应增长。

根因是评估/晋级链断裂。
人工恢复方向: 读最新 Bot 数据 → 手动判定 → 更新 progress.json → 重启驱动链。
```
