# auto-batch-request.json 生命周期

## 四种状态速查

| 你看到什么 | 实际状态 |
|-----------|---------|
| request.json 存在，result.json 不存在，Editor.log 无 Bot Batch | **未拾取** — Unity 还没处理 |
| request.json 存在，result.json 不存在，Editor.log 有 `[Bot Batch] Level Lxx` | **正在跑** — 别动它 |
| request.json 存在，result.json 也存在 | **跑完了** — request 还没被删干净，可以读 result |
| request.json 不存在，result.json 存在 | **跑完了** — 正常状态 |
| request.json 不存在，result.json 不存在 | **空闲** — 可以提新请求 |

## 陷阱：result 报告成功但 export 目录不存在

**2026-07-07 实例**: `auto-batch-result.json` 的 `outDir` 指向 `telemetry/bot/90-90-2026-07-07T11-19-33/L90-90-T1-...-batch-range`，但该目录**实际上不存在**。`bot/` 父目录 mtime 虽有更新（11:19:57），子目录却未持久化。

**根因推测**: Unity 的 `BlastBotAutoBatchTrigger` 在 `WriteResult()` 后 `TryDelete()` request.json，但 export 写入（`EditorUtility.RevealInFinder` / `ExportCampaignResultToExcel`）可能因弹窗被拦截、Unity 重编译或文件系统问题而未完成。

**检查步骤**:
```bash
# 验证 outDir 是否真实存在
ls -la "/c/Users/.../telemetry/bot/$(cat BuildLogs/auto-batch-last-export.txt | grep -oP '[^/]+$' | sed 's/\\r//')/" 2>&1
# 或直接解析结果 JSON 的路径
python -c "import json; print(json.load(open('BuildLogs/auto-batch-result.json'))['outDir'])"
```


## 关键陷阱

**"request.json 存在" ≠ "Unity 没拾取"。** 代码执行顺序是：

```
RunBot() → WriteResult() → TryDelete(request.json) → _isRunning = false
```

所以跑的过程中 request.json 一直存在。必须配合 Editor.log 和 result.json 判断。

## 判断当前状态四步法

```bash
# 1. request 存在？
ls BuildLogs/auto-batch-request.json

# 2. result 存在？
ls BuildLogs/auto-batch-result.json

# 3. Editor 日志在跑？
grep "Bot Batch" "%LOCALAPPDATA%/Unity/Editor/Editor.log" | tail -3

# 4. 综合判断
#    request有 + result无 + log有BotBatch = 运行中
#    request有 + result有               = 跑完了
#    request无 + result有               = 跑完了
#    request有 + result无 + log无BotBatch = 未拾取
```

## Request JSON 结构

auto-batch-request.json 的实际键名（CS 端 `BlastBotAutoBatchTrigger` 解析的字段）：

```json
{
  "levelSpec": "52,55,56,57,59,69,74,87,96",
  "runCount": 400,
  "levelFolder": "test",
  "tiersCsv": "1,2,3,4,5",
  "recordReplay": false,
  "tag": "verify-round3"
}
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `levelSpec` | string | **逗号分隔**的关卡号列表。注意不是 `tierGroup` 也不是 `levels` |
| `runCount` | int | 每档运行局数（如 400） |
| `levelFolder` | string | 导出子目录名（如 `test`） |
| `tiersCsv` | string | 逗号分隔的档位编号（如 `1,2,3,4,5`） |
| `recordReplay` | bool | 是否录制回放 |
| `tag` | string | **可选**。批次标签用于标识批次用途，如 `verify-round3`（第三轮验证）、`auto-round1`（首轮自动调优）。这个标签不出现在 bot 目录名中，但会出现在 result.json 的回传中 |

**注意：不要在 request 中使用 `tierGroup`、`levels` 等其他键名——Unity 端的 JSON 解析器只认以上字段。**
