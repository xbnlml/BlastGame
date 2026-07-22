# AssetDatabase 刷新与 request 提交可靠方法

## 标准提交流程

1. **patch asset** — `patch` 替换 `DynamicDifficultyConfigs:` 区块
2. **聚焦 Unity** — `subprocess.Popen`（非 `subprocess.run`）调用 AppActivate，避免 PowerShell 管道 hang
3. **等待 30s** — 给 Unity 足够时间检测文件变化并触发 AssetDatabase.Refresh
4. **提交 request** — 写 `auto-batch-request.json`

## request 消费超时处理

提交后 120s 未消费：

1. **聚焦 Unity**（AppActivate fire-and-forget）→ 等 60s
2. **delete-recreate 技巧**：删掉 `request.json` → 等 3s → 重新写相同内容 → 等 120s
3. 重试 3 次仍不消费 → **重启 Unity**（杀进程→重开）
4. 重启后等 60s → 重新提交

delete-recreate 触发 Unity PollForRequest 重新检查文件，成功率最高。

## 白跑检测（跑后）

Bot 完成后：读 `campaign-attempts.csv` 第一行 `startDifficulty`，比对期望值。不匹配则：
- 该轮不计入 6 轮探针上限
- 检查 asset 文件内容（grep StartDifficulty）确认文件正确
- 检查 Unity 是否加载了新配置（重启后 100% 正确）

## 已知失败模式

| 失败表现 | 根因 | 修复 |
|---------|------|------|
| request 不消费 | AppActivate 未执行（subprocess.run hang） | 改用 Popen |
| 跑出旧配置 | AssetDatabase 未刷新 | 重启 Unity |
| R1 全部超时 | 批跑未提交失败，但 timeout 太长 | 缩短 poll 到 180s |
