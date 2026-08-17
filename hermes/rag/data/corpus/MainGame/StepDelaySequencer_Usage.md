# StepDelaySequencer Usage

## 目标

- 统一串行步骤编排用法：按入队顺序执行、每步可延时、支持中途停止。
- 适用于“返回大厅演出”“多段领奖表现”“异步流程分步提交”等场景。

## 代码入口

- 实现：`Assets/GameModule/Common/Script/StepDelaySequencer.cs`
- 现成示例：`Assets/GameModule/GameMain/Script/UI/UIGameWinView.cs`

## 最小用法

```csharp
private readonly StepDelaySequencer<MyContext> _sequencer = new StepDelaySequencer<MyContext>();

private async UniTask RunFlowAsync(MyContext context)
{
    _sequencer.Clear();
    _sequencer.Enqueue("StepA", StepAAsync);
    _sequencer.Enqueue("StepB", StepBAsync, 0.1f);
    _sequencer.Enqueue("StepC", StepCAsync);

    await _sequencer.StartAsync(context);
}

private UniTask StepAAsync(MyContext context, CancellationToken ct)
{
    // step logic
    return UniTask.CompletedTask;
}
```

## 行为约定

- `Enqueue`：只负责追加步骤，不会立即执行。
- `StartAsync`：按当前队列顺序串行执行；若已在执行（`IsRunning=true`）会忽略本次启动。
- `Stop`：请求取消当前执行链；正在跑的步骤会收到取消 token。
- `Clear`：清空未执行步骤，不会中断当前已在执行的步骤。

## 推荐接入模式

- **启动前先 `Clear`**：避免遗留步骤串入新流程。
- **窗口关闭时 `Stop + Clear`**：防止界面销毁后异步步骤继续跑。
- **步骤函数保持幂等**：允许流程被取消后再次重试。

## 常见问题

1. 重复调用 `StartAsync` 没反应：
   - 原因：上一条序列仍在运行。
   - 处理：等待结束，或先 `Stop` 再按需重建队列。

2. 步骤延时不生效：
   - 先确认 `Enqueue(..., delaySeconds)` 传入的是该步骤的“执行前延时”。

3. 中途取消后状态残留：
   - 在 `finally` 或 `OnHidden` 做 UI 状态恢复，并调用 `Clear`。
