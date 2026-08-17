# Tier 映射调试参考

> **根因已确认并修复。** 本文件仅供历史参考和未来排查。

## 根因

Python `write_ddc` 写 .asset 后，Unity batch mode 启动时可能使用旧二进制缓存，
导致 `DynamicDifficultyConfigs` 读取乱序。

## 修复

1. C# 入口 `BlastBotJenkinsBatchEntry.RunFromCommandLine` 增加：
   ```csharp
   AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate);
   ```

2. `BlastWorkbenchWindow.Bot.cs` 中 `RunBotBatchByLevelRangeForJenkins` 循环前：
   ```csharp
   AssetDatabase.Refresh();
   ```

## 排查步骤（修复后仍复现时使用）

### 第1层: 确认 batch mode 入口
```csharp
// BlastBotJenkinsBatchEntry.RunFromCommandLine
Debug.Log($"[BatchDebug] Processing tierIndex={tierIndex} forcedTier={forcedTier}");
```

### 第2层: request 创建
```csharp
Debug.Log($"[BatchDebug] Created request hash={requestHash} ft={forcedTier}");
```

### 第3层: runner 入口
```csharp
// BlastBotBatchRunner.Run
Debug.Log($"[BatchDebug] Run(hash={hash})");
```

### 第4层: 验证实际 tier
```csharp
Debug.Log($"[BatchAttemptDebug] requestHash={rHash} reqFT={reqFT} appliedTier={actualTier} sd={sd}");
```

### 第5层: DDC 解析
```csharp
Debug.Log($"[TierDebug] tier={tier} resolvedTier={resolved} tierIndex={idx} sd={cfg.sd}");
Debug.Log($"[TierDebug] configs[0].sd={configs[0].sd} configs[1].sd={configs[1].sd} ...");
```
