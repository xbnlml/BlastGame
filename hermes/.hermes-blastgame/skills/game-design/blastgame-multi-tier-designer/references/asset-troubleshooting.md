# Asset 写入/读取故障排查

## Tier 配置错乱（T1 读成 T5）

**特征：** 所有档位 CSV 中的 startDifficulty 值相同或错乱，WR 也相同——说明实际运行使用了同一配置。

**根因：** Python `asset_patcher.write_ddc` 正确写入了 .asset 文件（read_ddc 回读验证可通过），但 Unity batch mode 启动时用旧二进制缓存，未重新解析 YAML。

**修复（C# 侧）：**
```csharp
// BlastBotJenkinsBatchEntry.cs — 入口处
AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate);

// BlastWorkbenchWindow.Bot.cs — 批跑循环前
AssetDatabase.Refresh();
```

两处确保 asset 在加载前重新导入。此修复已在 submit_batch_unity.py 流程中生效。

**历史：** 排查耗时约 6 批跑（每批 15-30 分钟）。走弯路包括：
- 猜 T1↔T5 索引互换 hack（错误，已删除）
- 逐个加 C# Debug.Log 到 ResolveTierDifficultyConfig 等函数
- 怀疑 dedup 机制导致结果复用
- 最终确认为 AssetDatabase 缓存
