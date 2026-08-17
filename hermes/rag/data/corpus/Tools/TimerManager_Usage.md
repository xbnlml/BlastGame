# TimerManager 使用说明（int 句柄版）

> **AI 使用提示**：新增、移除或排查定时器时读取本文；优先使用返回的 `int timerId`，UI/对象销毁时检查生命周期并移除定时器。

## 位置

- 实现文件：`Assets/GameModule/Common/Script/TimerManager.cs`
- 句柄规则：所有 `Add*` 方法都返回 `int timerId`，用于后续移除

## 核心约定

- 不再使用 `string key`。
- `timerId` 在每次 `Add*` 时自增（内部 `_nextTimerId` 从 `1` 开始）。
- UI 关闭时必须移除定时器，避免回调悬挂。

## API 速查

### 1) 秒级循环

```csharp
int timerId = TimerManager.Instance.AddLoopSeconds(
    intervalSeconds: 1f,
    callback: OnTick,
    owner: this,
    executeImmediately: false,
    ignoreTimeScale: true
);
```

等价方法：`AddListener(...)`

### 2) 帧级循环

```csharp
int timerId = TimerManager.Instance.AddLoopFrames(
    intervalFrames: 5,
    callback: OnTickFrame,
    owner: this,
    executeImmediately: false
);
```

等价方法：`AddFrameListener(...)`

### 3) 一次性延时

```csharp
int timerId = TimerManager.Instance.AddDelay(
    delaySeconds: 2f,
    callback: OnDelayDone,
    owner: this,
    ignoreTimeScale: true
);
```

### 4) 整秒倒计时（回调剩余秒）

```csharp
int timerId = TimerManager.Instance.AddCountdown(
    totalSeconds: 30,
    onTick: remainSeconds => UpdateText(remainSeconds),
    onComplete: OnCountdownComplete,
    owner: this,
    ignoreTimeScale: true,
    tickIntervalSeconds: 1f
);
```

### 5) 截止型计时（回调剩余浮点秒）

```csharp
int timerId = TimerManager.Instance.AddDeadline(
    totalSeconds: 5.5f,
    onTick: remainSeconds => UpdateRemain(remainSeconds),
    onComplete: OnDeadlineReached,
    owner: this,
    ignoreTimeScale: true,
    tickIntervalSeconds: 0.2f
);
```

等价方法：`AddUntil(...)`

## 移除与生命周期

### 按 `timerId` 移除

```csharp
TimerManager.Instance.RemoveListener(timerId);
timerId = -1;
```

### 按 owner 批量移除（推荐在 UI 销毁时）

```csharp
TimerManager.Instance.RemoveAllByOwner(this);
```

### 清空所有

```csharp
TimerManager.Instance.ClearAll();
```

## UI 推荐模式（循环列表场景）

- 列表层只开 **1 个** 秒级循环定时器（不要每个 item 开一个）。
- item 数据存绝对结束时间（例如 `endTimestamp`）。
- 每个 tick 仅刷新可见 item 的剩余时间文本。

示例参考：

- `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelView.cs`
- `Assets/GameModule/HomeModule/Script/UI/UIHomeLevelActivityItem.cs`

## 跨天与日索引

- 全局跨天刷新由 `TimerManager.Instance.StartDailyReset()` 启动，跨天时派发 `BlastMessageType.OnDayRefresh`。
- App 从后台恢复后建议调用 `TimerManager.Instance.CheckDayChangeImmediate()` 立即补检。
- 业务模块优先订阅 `OnDayRefresh`，保持统一入口。
- 如需按统一偏移计算天索引，使用：

```csharp
var dayIndex = TimerManager.ResolveDayIndex(serverSeconds);
```

- 需要自定义偏移时：

```csharp
var dayIndex = TimerManager.ResolveDayIndex(serverSeconds, timezoneOffsetSeconds);
```

## 常见坑

- `intervalSeconds <= 0`、`intervalFrames <= 0`、`tickIntervalSeconds <= 0` 会注册失败（返回 `-1`）。
- 回调传 `null` 会注册失败（返回 `-1`）。
- 如果你不保存 `timerId`，后续只能依赖 `RemoveAllByOwner(owner)`。
- 大量 item 场景不要每项独立注册 timer，优先“列表级单 timer”。
