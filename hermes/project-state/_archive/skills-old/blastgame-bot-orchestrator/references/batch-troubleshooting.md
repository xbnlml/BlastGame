# Bot 批跑排障参考

本文件记录 BlastGame Bot 批跑过程中遇到过的故障及其排查方法。新增故障时追加到末尾。

---

## 故障清单

### 2026-07-01：Unity .asset YAML 缩进错误

**现象**：所有批跑结果均为 100% WR（winCount=runCount, failCount=0, failBucketDistribution 全零）。批次在 1-2 秒内完成全部档位。

**根因**：`DynamicDifficultyConfigs:` 下的 `- StartDifficulty:` 使用了 2 空格缩进，但 Unity YAML 解析器要求 4 空格。Unity 解析失败时静默降级为默认配置（无难度），导致 Bot 瞬间通关。

**排查过程**：
1. 先怀疑是参数配置本身问题（恢复已知好用的 L80 variant A 配置 → 仍然 100%）
2. 发现 `read_asset_combo` 返回 9 个配置而不是 5 个（残留旧数据）
3. 修复残留后仍 100% → 发现是缩进问题
4. 修正到 4/6 空格后恢复正常

**证据**：
- 修复前：L80 T1=100%（400局全通）
- 修复后：L80 T1=92%（正常值）

**修复脚本**：`Doc/AI/multi-tier-designer/scripts/fix_asset_patch.py`（final version）

### 2026-07-07：monitor_bot.py false negative（永久等待）

**现象**：L89 批跑完成后，pipeline 卡死 3 小时。monitor_bot.py 进程存活但不返回。`auto-batch-last-export.txt` 存在且有完整数据，但 monitor 不退出。

**根因**：时序竞争条件 — monitor_bot.py 启动时间 (03:04:47) 晚于 `auto-batch-last-export.txt` 最后写入时间 (03:04:40)。monitor 记录当前 mtime 后等待变化，但 export 文件不会再有新写入，导致 `while True: time.sleep(1); check mtime` 永久循环。

**排查过程**：
1. `read_file pipeline-progress.json` → levels_done=13（未变），mtime=03:00（3h前）
2. `find -mmin -30` → bot 目录 — 无（全部 >30min）
3. `process(action='list')` → monitor_bot.py 运行中，启动于 03:04
4. 读 monitor_bot.py 源码 → 确认它只监控 `auto-batch-last-export.txt` mtime
5. 读 `auto-batch-last-export.txt` → 内容指向 L89-T5，mtime=03:04:40
6. 读 `auto-batch-result.json` → `success: true`，`finishedUtc` = 03:04:40
7. 对比 `ps` 输出的进程启动时间 (03:04:47) 与 export 最后时间 (03:04:40) → monitor 晚了 7 秒启动

**教训**：
- monitor_bot.py 的 mtime 等待机制不可作为唯一完成信号。必须同时使用目录轮询（检查 `telemetry/bot/{lv}-{lv}-*/` 出现）作兜底。
- 10min 超时检测后应先判断场景 A（data ready, monitor stuck）vs 场景 B（no data, batch still running），避免不必要地重启 Unity。
- 日常检查 `auto-batch-result.json` 比等 monitor 通知更快。
- **诊断技巧**：用 `cat /proc/<pid>/status | grep State` 查看 monitor 进程状态。`S (sleeping)` 表示空闲等待（可能已错过信号），`R (running)` 表示正在活跃执行。2026-07-07 实测 monitor 在 sleeping 状态 idle 了 3h40m，未做任何工作。

**修复方向**：可将 monitor 启动逻辑改为：启动时先检查 export 文件 mtime → 如果已非最新则立即读取结果退出，不进入等待循环。

### 2026-07-01：大批次 AssetDatabase.Refresh 耗时

**现象**：修改 31 个 asset 文件后提交批跑，等了 6 分钟才有反应。

**根因**：Unity 的 `AssetDatabase.Refresh(ForceUpdate)` 需要重扫描所有修改过的 asset 文件。31 个文件同时修改耗时 ~6 分钟。

**教训**：改完 asset 文件后不要立即提交 bot 请求。等 Editor 编译/刷新完成（Unity 进程 CPU 稳定后再提交）。

### 2026-07-16：auto-batch-result.json 从不写入

**现象**：Bot 跑完 5 档全部 CSV 数据齐备，但 `auto-batch-result.json` 从未出现。submit_batch 等不到 result 无限超时。

**根因**：Unity 的 `BlastBotAutoBatchTrigger` 不保证写入 `auto-batch-result.json`。多个批次确认：R1/R2/R3 全部不写 result.json，但 bot 目录正常产出数据。可能是 `JsonUtility.ToJson` 或文件写入异常被静默吞掉。

**修法**：submit_batch.py 改为轮询 bot 目录而不是等 result.json。新监控逻辑：
1. 提交前记录 `telemetry/bot/` 的已有目录集合
2. 提交后每 10s 检查新目录
3. 新目录有 **5 个 T1-T5 子目录 + 各含 campaign-summary-*.csv** → 判定完成
4. 不依赖 `auto-batch-result.json`、`auto-batch-last-export.txt`、monitor_bot.py

### 2026-07-16：BlastBotAutoBatchTrigger 批次间停止轮询

**现象**：一次批次完成后，后续新 request 永远不会被 Unity 消费。Unity 进程在运行，CPU 正常，但 `PollForRequest` 不再触发。

**根因**：`BlastBotAutoBatchTrigger` 使用 `EditorApplication.update` 注册回调。批次完成后回调退出或被注销，后续 request 不被检测。Unity 重启恢复。

**规律**：每批次结束后 **必须重启 Unity** 才能提交下一批。

**推荐流程**：
```bash
taskkill /F /IM Unity.exe
python tools/restart_unity.py --start
sleep 90  # 等 Unity 加载完成
rm -f BuildLogs/auto-batch-request.json
python scripts/submit_batch.py "56,57,71,86" --games 400 --force
```

