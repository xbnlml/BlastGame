# 卡死/故障恢复参考

## request 消费超时（提交后 120s 未消费）

1. 聚焦 Unity：`(New-Object -ComObject WScript.Shell).AppActivate("BlastGame")`（timeout=5）
2. 等待 60s
3. 仍未消费 → delete-recreate request → 等 120s
4. 3 次重试后仍不消费 → **重启 Unity**（杀进程→重开）→ 等 30s → 重新提交
5. ⚠️ 不跳过该关

## monitor/export 超时（10min+ 无通知）

### 场景 A：monitor_bot.py false negative（启动太晚）

monitor_bot.py 在 `auto-batch-last-export.txt` **已写入后**才启动 → monitor 记录当前 mtime，进入死循环等变化 → 实际上批次已完成，但 monitor 永远不退出。

**识别：** `ps | grep monitor_bot` 确认进程存在且运行时间 >5min；对比 `auto-batch-last-export.txt` mtime 与 monitor 进程启动时间，前者早于后者。

**恢复（两步）：**
1. 杀 monitor 进程（`kill <pid>` 或 `process(action='kill', session_id=...)`）
2. 直接读 `BuildLogs/auto-batch-result.json` → 取 `outDir` 确认 export 数据完整性 → 跳过 monitor，直接进入 Step 6 判定
3. ⚠️ **不重启 Unity，不重新提交** — 数据已就绪，只是 monitor 没通知到

### 场景 B：真正超时（批次未完成）

1. 检查 `telemetry/bot/{lv}-{lv}-*/` 是否有数据 → 有则读结果继续
2. 无数据 → 检查 Unity 进程（PowerShell Get-Process Unity）
3. 进程存在 → 聚焦再等 5min
4. 仍无 → **重启 Unity** → 重新提交
5. ⚠️ 不跳过该关

## Unity 崩溃（进程消失）

1. 自动重启：`Unity.exe -projectPath ...`
2. 等 30s 确认 ready（grep "Internal_CallUpdateFunctions"）
3. 聚焦 Unity
4. 恢复中断的任务
5. ✅ 这是故障恢复，不是随意重启

## Unity 编译错误阻塞（ExitCode 3/4 + CS0117）

**现象：**
- `auto-batch-request.json` 存在但始终不被消费（Unity 无法进入 Play Mode）
- `unity-launch-*.log` 含 `error CS0117: 'XXX' does not contain a definition for 'YYY'`
- Unity 进程退出码为 3（编译错误）或 4（脚本编译失败），如 `ExitCode: 3 Duration: 1s10ms`
- 无新 bot 目录产生
- `Editor.log` 中无 PollForRequest 活动

**排查命令：**
```bash
# 1. 确认编译错误存在
grep "CS0117\|error CS" BuildLogs/unity-launch-*.log | tail -10

# 2. 查看 Unity 退出码
grep "ExitCode:" BuildLogs/unity-launch-*.log | tail -5
# ExitCode: 3 = 编译错误，ExitCode: 4 = 脚本编译失败

# 3. 找出缺少的字段名
grep -oP "'[^']+' does not contain a definition for '[^']+'" BuildLogs/unity-launch-*.log | sort -u
```

**根因：** Unity C# 脚本引用了 `BlastBotBatchRunRequest`（或其它类）上不存在的字段。可能是：
- 新 `.cs` 文件写入了依赖新字段的代码，但 `BlastBotBatchRunRequest.cs` 未同步更新
- 代码合并/回退导致的新旧版本不一致
- Agent 修改了 `BlastWorkbenchWindow.Bot.cs` 添加了新功能但忘记更新数据类

**恢复步骤（必依顺序）：**

1. **不重启 Unity！** 重启无法解决编译错误，ExitCode 3 是确定的。
2. **定位缺失字段：** 从 grep 输出中提取缺失的字段名（如 `adaptiveStopEnabled`, `bayesStdThreshold`）和引用它们的类。
3. **找到数据类定义：** 通常是 `BlastBotBatchRunRequest.cs` 或 `BlastBotBatchRunDef.cs` 等，在 `Assets/GameModule/Editor/Bot/` 下：
   ```bash
   grep -l "class BlastBotBatchRunRequest" Assets/GameModule/Editor/Bot/*.cs
   ```
4. **补齐字段定义：** 将缺失字段加入对应类的属性定义中，保持与引用代码一致的类型和默认值。
5. **触发重编译：** Unity 检测到 `.cs` 变更后自动触发 domain reload。等待 30s 确认无新错误。
6. **重新提交 request：** 删 `auto-batch-request.json` → 等 3s → 重新写入。
7. **验证消费：** 120s 内 Unity 应该拾取并开始跑。
8. **如果仍有编译错误：** 重复步骤 2–5，或检查引用处是否还有其他缺失的依赖。

⚠️ **不要通过重启 Unity、启动新编辑器实例或重新导入所有资源来修复编译错误。** 编译错误是代码问题，不是运行时问题。真正的修复是补齐缺少的字段/类定义。

## TryDelete 失败循环（request.json 永不删除）

**现象：**
- 同一 `auto-batch-request.json` 持续存在（content 不变或相似）
- Bot 目录持续增长但均为同一 level（如 L93 重复 10+ 次）
- `levels_done` 冻结

**根因：** Unity 的 `BlastBotAutoBatchTrigger.RunBot → TryDelete` 环节失效（权限问题、文件锁、异常退出路径未覆盖 delete）。每次 PollForRequest 看到 request.json 尚在 → 重新执行 → 生产新目录 → TryDelete 再次失败 → 循环。

**检测：**
```bash
# 记录 request content hash 跨次比较
md5sum BuildLogs/auto-batch-request.json
# 检查同一 level 的 bot 目录数量（如 L93）
ls -d telemetry/bot/*93* 2>/dev/null | wc -l
# 对比两次检查的结果 → 增长则命中循环
```

**恢复步骤：**
1. 删除残留 request.json：`rm BuildLogs/auto-batch-request.json`
2. 评估最新一次 bot 运行结果（读最新目录的 CSV 数据）
3. 根据判定结果更新 `progress.json`（标记 done 或 ggk）
4. 写入**新** request.json（保证 content 不同——不同 levelSpec 或不同 runCount/tag。避免 Bot 再次命中相同的 request）
5. 如果 TryDelete 持续失败，每次提交新 request 前先删旧文件再写

**关键区别 vs 其他 stall 类型：**

| 类型 | request.json | bot 目录 | 恢复 |
|------|-------------|---------|------|
| 正常批次间间歇 | 不存在 | 无新活动，但前次批次完整 | 等下次提交 |
| Stale request（§4） | 存在但 mtime 老 | 无新活动 | 删 request → 提交新请求 |
| **TryDelete 循环** | **存在且 mtime 可能新** | **同一 level 目录持续增长** | 删 request → 评估最新数据 → 提交**不同**新请求 |
| request 消费超时 | 存在（未被消费） | 无 | 聚焦 Unity → 重试消费 |

## 全部完成

- pending 列表变空 → 输出汇总表（已完成关/待确认关/故障关）
- 显式停止流程
