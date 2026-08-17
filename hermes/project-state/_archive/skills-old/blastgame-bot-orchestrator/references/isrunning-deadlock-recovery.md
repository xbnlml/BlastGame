# `_isRunning` 死锁恢复

## 症状

PollForRequest 不消费新请求。`request.json` 一直存在，`result.json` 不存在。
Editor.log 中有 `NullReferenceException: Object reference not set to an instance of an object`。

## 原因

`TryRunFromRequestFile()` 的 `finally` 块中 `window.Close()` 抛出 NRE。
NRE 传播阻止了第 136 行 `_isRunning = false` 执行，`_isRunning` 永久为 true。

## 修复

**已在 `BlastBotAutoBatchTrigger.cs` 中应用 try-catch 包裹 `window.Close()`：**

```csharp
finally
{
    if (window != null)
    {
        try { window.Close(); }
        catch { /* ignore Close() NRE — window already destroyed */ }
    }
}
```

## 恢复步骤

1. 修改 `.cs` 文件触发 Unity domain reload → 静态变量 `_isRunning` 重置为 false
2. **不写 `__ForceReload.cs`** — 它本身就是触发方式，但会引发问题。修改已有 `.cs` 文件更可控
3. 等 Unity 重编译完成（~20s）
4. 确认 Editor.log 有 `PollForRequest` 日志行
5. 写新 request.json → PollForRequest 自动消费

## 预防

- 正常提交**只写 request.json**，不触发 domain reload
- 旧 request 未清前不写新 request
- 确认 `_isRunning` 不为 true 后再提交
