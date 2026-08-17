# 提交方式

## Batch Mode（推荐）

Unity 项目自带 batch mode 入口：
- Bot 批跑：`BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine`

命令行：
```
".../Unity.exe" -batchMode -nographics -projectPath "..." -executeMethod BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine -BlastBotBatchLevels "56,57" -BlastBotBatchRunCount 400 -BlastBotBatchTiers "1,2,3,4,5" -BlastBotBatchLevelFolder "test" -logFile - -quit
```

Python 封装：`scripts/submit_batch_unity.py`

优势：无 Editor window 崩溃、无 `_isRunning` 锁死、`-logFile -` 实时看进度、退出码正常。
限制：不能和 Unity Editor 同时运行（license 冲突）。License warning 无害。

## Editor Trigger（备用）

依赖 `BlastBotAutoBatchTrigger`（`EditorApplication.update` 轮询 `request.json`）。
批次间必须重启 Unity（trigger 跑完就死）。

## --tiers 必填

两个 submit 脚本均不设默认值。不填直接报错退出，提示用法。

## Monitor

`tools/monitor_bot.py` — 独立 bot 目录监控，检测 5 档齐全。不可删除。
