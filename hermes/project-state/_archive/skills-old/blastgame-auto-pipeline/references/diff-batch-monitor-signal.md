# diff_batch_monitor.json — 外部监控进程信号源

> 管道在执行过程中可能运行一个独立的 Python 监控脚本，持续轮询 Unity 日志并写入 `diff_batch_monitor.json`。此文件提供 Unity 内部的实时活动信息，与看门狗的 `pipeline-progress-check.json`（外部文件系统状态）互补。

## 路径

```
D:\download\reasonix\project-state\diff_batch_monitor.json
```

## Schema

```json
{
  "time": "07:21:44",
  "log_mtime": "15:23:01",
  "log_kb": 4333,
  "cur_level": "?",
  "cur_done": "?",
  "tier_dirs": {}
}
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `time` | string | 监控脚本最近一次轮询的时间（HH:MM:SS） |
| `log_mtime` | string | Unity 日志文件上次修改的时间（HH:MM:SS，可能是跨天的，注意比对 `time`） |
| `log_kb` | int | Unity 日志文件大小（KB），可用于判断是否有新输出 |
| `cur_level` | string | 从日志中提取的当前正在处理的关卡号。`"?"` 表示未匹配到 `Level L(\\d+)` 行 |
| `cur_done` | string | 从日志中提取的已完成的关卡数（如 `"12"` 表示 12/49）。`"?"` 表示未匹配 |
| `tier_dirs` | object | 监控脚本过滤到的 bot tier 子目录的状态。key=Tier 前缀（如 `T1`），value=文件数和大小 |

## 检测方法

```bash
# 检查 diff_batch_monitor.json 是否存在
ls -la /d/download/reasonix/project-state/diff_batch_monitor.json 2>/dev/null

# 检查监控脚本进程（通常是 python 进程，用 -c 启动）
ps -W | grep -i "diff_batch_monitor"

# 或者查找包含 bot 监测脚本的进程（更可靠）
ps -W | grep -i "bot" | grep python
# 特征：一个监视 unity-launch-v{N}.log 的 Python 进程
```

## 活信号解读

| 信号 | 解读 |
|------|------|
| `time` 接近当前时间 | 监控脚本在正常运行（轮询间隔通常 120s） |
| `log_mtime` 接近 `time` | Unity 日志最近有输出（Unity 在活动） |
| `cur_level` 不是 `"?"` | Unity 正在处理一个可以识别的关卡批次（有 `Level L(\\d+)` 行） |
| `tier_dirs` 非空 | 监控脚本检测到了新产出的 bot 数据 |
| `log_kb` 增长较快 | Unity 日志在快速写入（活跃处理中） |

| 反信号 | 解读 |
|--------|------|
| `time` 远早于当前时间 | 监控脚本可能已挂起或退出 |
| `cur_level` 长期为 `"?"` | 监控脚本的正则 `Level L(\\d+) \\((\\d+)/49\\)` 在日志中无匹配。可能原因：(a) Unity 未在处理批次（空闲），(b) 日志轮转压缩，(c) 日志文件路径变了 |
| `tier_dirs` 为空 | 监控脚本的目录过滤器（字符串 `startswith`）不匹配当前 bot 目录命名格式 |

## 常见陷阱：Stale 过滤器

> **这是最常发生的误报来源。** 监控脚本在启动时通过一个硬编码的字符串匹配过滤 bot 目录（如 `d.startswith('52-100-2026-07-08T01-36')`）。当管道后续提交不同前缀的新批次时，监控脚本的过滤器不再匹配任何目录 → `tier_dirs` 永远为空 → 看门狗误以为无 Bot 产出。

### 检测方法

```bash
# 1. 查看监控脚本的启动命令行，提取目录过滤器
ps -W | grep python | grep -i "bot\|monitor\|batch"
# 输出示例:
#   python3.exe -c "import os,...; new_dirs = [d for d in sorted(os.listdir(bot_dir)) if d.startswith('52-100-2026-07-08T01-36')]"

# 2. 提取过滤器字符串
#   从命令行中找到 d.startswith('...') 的内容

# 3. 比对最新 bot 目录的前缀
ls -t /c/Users/Administrator/Documents/BlastGame/telemetry/bot/ | head -5
#   如果过滤器前缀和最新目录前缀不匹配 → 过滤器已 stale
```

### 2026-07-15 实例

```
监控脚本命令行过滤器: d.startswith('52-100-2026-07-08T01-36')
当前最新 bot 目录:     59_63_68-69-2026-07-15T04-16-38
❌ 前缀不匹配 → tier_dirs 永远为空，监控脚本实效
```

**影响：** 看门狗读 `diff_batch_monitor.json` 时看到 `tier_dirs: {}`，可能误判为"无 Bot 产出"。但实际上 Bot 一直有产出，只是监控脚本的过滤器在 7 天前就失效了。

### 修复方法

终止旧的监控进程，使用更新的过滤器重新启动。或改造监控脚本使其自动匹配最新目录前缀，而非硬编码。

## 与 watchdog 集成的用法

看门狗可以将 `diff_batch_monitor.json` 作为辅助信号源，与主检查流程并行：

```json
// pipeline-progress-check.json 扩展字段
{
  "diff_batch_monitor": {
    "time": "07:21",
    "log_mtime": "15:23",
    "cur_level": "?",
    "cur_done": "?",
    "tier_dirs_count": 0,
    "filter_stale": true
  }
}
```

| `filter_stale` | 含义 |
|--------------|------|
| `false` | 过滤器匹配当前目录 → `tier_dirs` 可信 |
| `true` | 过滤器不匹配当前目录 → `tier_dirs` 不可信，不应作为"无 Bot 产出"的依据 |

当 `filter_stale=true` 时，看门狗应忽略 `tier_dirs` 信号，不在判断逻辑中使用它。

## 多实例检测

有时会出现**多个同脚本的 Python 进程同时运行**（如 PID 23556 和 37212 运行完全相同的监控代码）。这通常是因为：
- Hermes 网关重启后启动了新实例，旧实例未清理
- 同时有 python.exe 和 python3.exe 两个版本的相同脚本

**检测：** `ps -W | grep python | grep -c "bot\|monitor"` 如果 > 1，说明有多实例。

**影响：** 无直接危害（脚本只写不读，两个实例覆盖同一文件），但说明环境中有残留进程。可通过 `taskkill /PID <pid>` 清理。
