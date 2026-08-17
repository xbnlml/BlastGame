# BlastBotAutoBatchTrigger 恢复

## 问题

Unity 的 `BlastBotAutoBatchTrigger` 在每次批次完成后可能停止工作，表现为 request.json 提交后 Unity 不消费（文件不被删除）。

## 根因

```csharp
static BlastBotAutoBatchTrigger() {
    EditorApplication.update += OnEditorUpdate;
}

private static void OnEditorUpdate() {
    if (_isRunning) return;          // ← 上一轮崩溃后 _isRunning 永远为 true
    ...
    _isRunning = true;
    TryRunFromRequestFile(...);      // ← 如果这里崩溃，_isRunning 不被释放
    _isRunning = false;
}
```

触发流程：
1. TryRunFromRequestFile 调用 window.RunBotBatchByLevelRangeForJenkins(...)
2. 如果配置有误（如 ratios/sc 不匹配），RunBotBatchByLevelRangeForJenkins 抛异常
3. catch 块捕获异常并记录日志
4. finally 块执行 window.Close() — **但 window 可能为 null（CreateInstance 失败），导致 NRE**
5. _isRunning 永远保持 true，下次 EditorApplication.update 直接 return

## 识别

```bash
ls "$BLASTGAME_REPO/BuildLogs/auto-batch-request.json"   # request 文件存在
tasklist /FI "IMAGENAME eq Unity.exe" /NH                  # Unity 进程存在
```

request 存在 + Unity 运行 + 超过 30s 未被消费 = trigger 失活。

## 恢复

### 方案 1：重启 Unity（推荐，可靠）

```bash
taskkill /F /IM Unity.exe
python tools/restart_unity.py --start
sleep 90                           # 等 Unity 完全加载
rm -f "BuildLogs/auto-batch-request.json"
# 然后重新提交
```

### 方案 2：domain reload（不一定行）

touch .cs 文件触发 Unity 重编译，重置所有静态变量：

```bash
echo "// reload $(date)" >> "$BLASTGAME_REPO/Assets/GameModule/Editor/Bot/BlastBotAutoBatchTrigger.cs"
```

等待 30-60s，如果仍不消费 → 走方案 1。

### 方案 3：修改 C# 修复（需要 Unity 重编译）

在 `BlastBotAutoBatchTrigger.cs` 的 `finally` 块加 null 检查：

```csharp
finally { if (window != null) window.Close(); }
```

同时确保异常路径释放 `_isRunning`：

```csharp
catch (Exception ex) { error = ex.ToString(); Debug.LogException(ex); }
finally { _isRunning = false; if (window != null) window.Close(); }
```

## 预防

- 每次提交前 `--dry-run` 验证配置（sc/ratios 匹配）
- 批次间必须重启 Unity（`taskkill` + `restart_unity.py --start`）
- 不要假设 Unity 的 EditorApplication.update 永久可靠
