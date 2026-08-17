# 同色攻击预测稳定化与普通块计数优化计划

## 1. 文档目的

本文用于交接当前未完成的 GameMain 性能优化，覆盖：

1. 修复同色攻击预测副本递归预测导致的 Unity Editor 栈溢出。
2. 将 Runtime 同色预测调整为仅在真实依赖变化时重建。
3. 保证预测副本执行路径在调用图上无法再次创建预测。
4. 完成 `RemainingNormalBlockCount` 的增量维护与旧扫描一致性验证。

主范围：`Assets/GameModule/GameMain/`。

业务规则真源：`Playbooks/game-main/sim.md`。攻击相关改动必须保持特殊块优先级、目标选择、攻击顺序、弹药消耗、胜负 Tick 与 Replay 结果不变。

## 2. 当前状态与已知事故

当前工作区存在未提交修改，禁止 reset、checkout 或覆盖现有 diff。

原先已有、与本任务无关的用户修改：

- `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Gameplay.cs`
- `Assets/GameModule/GameMain/Script/Runtime/BlastGameViewPresenter.cs`
- `Assets/GameModule/GameMain/Script/UI/BlastBoardView.cs`

本轮优化已修改的主要文件：

- `Script/Core/BlastTypes.cs`
- `Script/Level/BlastLevelLoader.cs`
- `Script/Runtime/BlastGameRollbackRuntime.cs`
- `Script/Runtime/BlastPowerUpHammer.cs`
- `Script/Sim/BlastAttackPrediction.cs`
- `Script/Sim/BlastAttackSystem.AttackOnce.cs`
- `Script/Sim/BlastAttackSystem.SpecialBlocks.cs`
- `Script/Sim/BlastAttackSystem.State.cs`
- `Script/Sim/BlastAttackSystem.Update.cs`
- `Script/Sim/BlastBoardClosing.cs`
- `Script/Sim/BlastEngine.cs`
- `Script/Sim/BlastGameLogic.cs`

2026-08-13 16:33:29 发生 Unity Editor 崩溃。崩溃报告：

`/Users/zhaokang/Library/Logs/DiagnosticReports/Unity-2026-08-13-163329.ips`

报告特征：

- 主线程 `EXC_BAD_ACCESS / SIGILL`。
- 访问落在 Stack Guard。
- `GC_clear_stack_inner` 重复递归。
- 托管 JIT 帧重复约 1700 层。
- 崩溃发生在 FixedUpdate，栈中包含 `MemberwiseClone`。

根因已经确认：

```text
GetColorAttackPlans
  -> BuildColorAttackPlans
  -> PredictNormalConsumableCountByColor
  -> CreatePredictionReplica
  -> predictedSystem.UpdateAttacks
  -> GetColorAttackPlans
  -> 再次 BuildColorAttackPlans
  -> 无限递归
```

旧实现通过预测副本的 `_cachedColorAttackPlanDirty = false` 偶然阻断嵌套预测。当前版本缓存改造删除了该状态，但没有建立新的结构边界，导致预测副本把空缓存视为 miss 并再次创建预测。

在完成第 4 节之前，不要运行同色双槽或多槽场景。

## 3. 最终不可变约束

- Runtime 顶层可以请求同色预测，但预测执行本身必须是叶子调用。
- 预测执行路径不得调用 `GetColorAttackPlans` 或 `BlastAttackPrediction`。
- Runtime 不得每 Tick 或每次 cooldown/ammo 变化都运行完整预测。
- Bot 每个 AttackSystem、预测副本、缓存和 Scratch 独立；禁止普通静态可变容器。
- 不共享预测 Dictionary，不复用与另一 State 绑定的目标引用。
- 保持攻击顺序、目标选择、弹药、击杀 runtimeId、胜负 Tick 和 Replay 签名一致。
- `RemainingNormalBlockCount` 永不小于 0，且与旧扫描口径完全一致。

## 4. 第一阶段：消除预测递归

### 4.1 拆分攻击编排和纯执行

将当前 `BlastAttackSystem.UpdateAttacks` 拆成三个职责：

```text
PrepareAttackFrame
  -> ResolveColorAttackPlans（仅顶层 Runtime/Bot）
  -> ExecuteAttackFrame（纯攻击规则执行）
```

建议入口：

```csharp
public void UpdateAttacks(...)
private void PrepareAttackFrame(...)
private void ExecuteAttackFrame(..., IReadOnlyDictionary<int, ColorAttackPlan> colorPlans)
```

`PrepareAttackFrame` 负责：

- Slot 引用和结构同步。
- cooldown 递减。
- attackOrder、readyShooters 构建。
- 底行和行目标准备。

`ResolveColorAttackPlans` 负责：

- 判断是否存在同色多槽竞争。
- 读取或重建昂贵预测缓存。
- 根据当前 ammo 轻量生成动态计划。

`ExecuteAttackFrame` 负责：

- 使用传入的 plans 选择射手和目标。
- 执行命中、队列消费、击杀、Closing、掉落和补块。
- 不得引用 `BlastAttackPrediction`。
- 不得调用 `GetColorAttackPlans`。

如果一次性抽取整个 `ExecuteAttackFrame` 风险过高，可以先抽取完成预测所需的内部执行入口，但最终必须保证预测 Runner 进入的方法体内不存在任何计划构建分支。

### 4.2 预测 Runner 只调用纯执行入口

`PredictNormalConsumableCountByColor` 改为：

```text
Clone State / Slots / SpawnContext
  -> CreatePredictionReplica
  -> PrepareAttackFrame
  -> ExecuteAttackFrame(plans: null)
```

禁止继续调用顶层 `UpdateAttacks`。

预测副本中的 `plans: null` 表示沿用旧逻辑的原始攻击执行，不代表缓存 miss，也不得触发新的 Forecast。

### 4.3 增加重入断言

增加 AttackSystem 实例字段：

```csharp
private bool _isBuildingColorForecast;
```

预测构建使用 `try/finally`：

```csharp
Debug.Assert(!_isBuildingColorForecast);
_isBuildingColorForecast = true;
try
{
    // build forecast
}
finally
{
    _isBuildingColorForecast = false;
}
```

该字段只用于发现未来回归，不作为正常流程的主控制条件。

Development 聚合：

- `nestedForecastRejectedCount`
- `maxObservedForecastDepth`

验收值必须分别为 0 和 1。

## 5. 第二阶段：拆分昂贵预测缓存与动态计划

### 5.1 只缓存昂贵值

缓存只保存：

```csharp
Dictionary<int, int> predictedConsumableCountByColor;
```

以下字段每次请求时按当前 Slot/ammo 轻量重算：

- `minAmmo`
- `preferredShooterIdx`
- `predictedConsumableCountHalf`
- `gateToMinAmmo`

不得缓存完整 `ColorAttackPlan` 后跨 ammo 变化直接复用。

### 5.2 空结果也是有效缓存

增加明确有效位：

```csharp
private bool _hasColorForecastCache;
```

缓存结果可以是 null、空 Dictionary 或颜色计数为 0。不得通过 `_cachedColorAttackPlans != null` 判断缓存有效，否则无计划局面会每 Tick重建。

### 5.3 完整缓存身份

缓存键至少包含：

```csharp
BlastGameState cachedState;
int cachedBoardTargetVersion;
int cachedSlotPlanVersion;
int cachedNormalAttackQueueVersion;
```

命中必须满足：

```csharp
_hasColorForecastCache
&& ReferenceEquals(state, cachedState)
&& 三个版本全部一致
```

State 引用必须参与比较，避免 Rollback、Replay restore 或换局后版本数字碰撞。

## 6. 第三阶段：精确定义版本边沿

### 6.1 boardTargetVersion

推进：

- Board 格子新增、移除或移动。
- Block 颜色变化。
- `health > 0` 与 `health <= 0` 之间跨边沿。
- 特殊类型、Gate/Snake/2x2 组结构变化。
- 底行目标可攻击状态变化。
- drop landing 从锁定跨到解锁，或从解锁跨到锁定。

不推进：

- `health 5 -> 4` 且仍存活。
- `closeRemainMs` 单纯递减。
- `dropLandRemainMs` 单纯递减但未跨过 0。
- cooldown、UI、动画和日志变化。

当前 `BlastGameState.SetBlockHealth` 每次 health 变化都会推进 `BoardTargetVersion`，必须修正为只检测存活边沿：

```csharp
var wasAlive = oldHealth > 0;
var isAlive = newHealth > 0;
if (wasAlive != isAlive)
    MarkBoardTargetChanged();
```

### 6.2 slotPlanVersion

每个 Slot 的依赖快照至少包含：

- piece 引用。
- color。
- lifeState 或结构性攻击能力。
- triangle。
- linkGroupId。
- linkedSlotIdx。
- linkRightSlotIdx。

推进：入槽、离槽、对象替换、颜色变化、合并、连体结构变化、Triangle 能力变化、状态跨边沿。

不推进：ammo、cooldown、`lifeStateRemainingMs` 单纯递减。

### 6.3 normalAttackQueueVersion

所有写操作收口到：

```csharp
RebuildNormalAttackQueue(...)
ConsumeNormalAttackQueueEntry(...)
ClearNormalAttackQueue(...)
RestoreNormalAttackQueueSnapshot(...)
```

队列构建、重建、消费、清理和 Snapshot restore 推进版本。禁止局部函数直接修改容器却不推进版本。

## 7. 第四阶段：避免普通命中每发重预测

昂贵预测值表示“从当前状态开始还能消费多少次普通攻击”。

如果发生普通命中且没有结构变化，可增量调整当前有效缓存：

```csharp
cachedPredictedConsumableCountByColor[sourceColor]--;
```

仅在以下条件成立时续用缓存：

- 本次命中 `targetSpecialKind == None`。
- 缓存当前有效。
- Board/Slot 没有同时发生结构变化。
- 结果不会小于 0。

同时推进 Queue 版本，并将缓存记录的 Queue 版本同步到新值，表示该次消费已经被缓存吸收。

如果命中同时导致目标死亡、底行变化、掉落、Pool/Queue 补块，则不做增量续用，让版本失配并在下一次请求时重建。

## 8. 第五阶段：预测结果原子提交

预测前捕获：

```csharp
var stateRef = state;
var boardVersion = state.BoardTargetVersion;
var slotVersion = _slotPlanVersion;
var queueVersion = _normalAttackQueueVersion;
```

预测结束后再次确认 State 引用和三个版本未变化。一致才写入缓存；不一致则丢弃结果并增加 `forecastDiscardedByVersionChangeCount`。

Runtime 当前仅主线程，此保护主要用于防未来改动和 Bot 错误共享 AttackSystem 实例。

## 9. 第六阶段：普通块剩余计数审查

唯一贡献函数：

```csharp
block != null && block.health > 0 && !block.isSpecial ? 1 : 0
```

要求：

- `SetBlock` 使用新旧贡献差值。
- `RemoveBlock` 通过统一入口更新。
- `SetBlockHealth` 仅在贡献变化时调整计数。
- `SetBlockSpecialState` 处理普通和特殊互转。
- Move 的 Remove + Set 最终净变化为 0。
- Queue/Pool refill 必须通过 `SetBlock`。
- Clone 直接复制计数，不重新扫描。
- 初始化完成后执行一次 `RecalculateRemainingNormalBlocks()`。
- Rollback/Replay restore 复制或重算后再进入 Tick。
- `TickCombatInternal` 胜负判断读取 O(1) 计数。

Development 断言保留旧扫描，但不得在预测 Clone 热路径或每个空闲 Tick 执行全盘扫描。

## 10. 诊断指标

仅 Development 聚合：

- `forecastRequestCount`
- `forecastCacheHitCount`
- `forecastEmptyCacheHitCount`
- `forecastRebuildCount`
- `forecastPassCount`
- `forecastIncrementalConsumeCount`
- `forecastDiscardedByVersionChangeCount`
- `nestedForecastRejectedCount`
- rebuild reason：State、Board、Slot、Queue

不得逐 Tick 输出日志。

## 11. 验证顺序

### 11.1 崩溃回归

- 同色双槽、三槽进入攻击。
- 连续运行数千逻辑 Tick。
- `nestedForecastRejectedCount == 0`。
- 最大 Forecast 深度为 1。
- Unity 日志中不再出现递归 `GC_clear_stack_inner`。

### 11.2 缓存频率

- Idle Tick 不重建。
- cooldown 递减不重建。
- ammo 减少不直接重建。
- 普通目标未死亡的命中走增量消费。
- Slot 状态跨边沿重建一次。
- 目标死亡、底行变化重建一次。
- 空结果后续命中 empty cache。
- Rollback 替换 State 后强制重建一次。

### 11.3 新旧逻辑对照

对比：

- predictedConsumableCount
- preferredShooterIdx
- gateToMinAmmo
- 每 Tick hit 顺序
- ammo
- killed runtimeId
- Board/Slot 最终签名
- 胜负 Tick

覆盖：

- 同色双槽/多槽、不同 ammo。
- Objective、Snake、Gate、2x2。
- Pool/Queue refill。
- FlyingIn、Closing、Merge。
- Hammer、Wand、Rollback。
- Replay restore。
- Bot Beam、Settle、多线程运行。

### 11.4 普通块计数

关键 Board transaction 后比较：

```csharp
state.RemainingNormalBlockCount == BlastGameLogic.CountRemainingNormalBlocks(state)
```

并确认计数永不小于 0、Clone 前后相等、胜利 Tick 与旧逻辑一致。

## 12. 提交顺序

必须拆成三个独立提交：

1. `fix(game-main): 消除同色攻击预测递归`
2. `perf(game-main): 收窄同色攻击预测缓存失效`
3. `perf(game-main): 增量维护普通块剩余计数`

每个提交分别执行：

- `git diff --check`
- `git diff --stat`
- 定向 C# 编译或 Unity Script Compilation
- 对应专项验证

第一个提交验证通过前，不继续缓存性能优化；第二个提交验证通过前，不提交普通块计数优化。

## 13. 新 Agent 开始工作的建议顺序

1. 读取本文件和 `Playbooks/game-main/sim.md`。
2. 查看当前 `git status --short`，明确三处原有用户 diff。
3. 只审查上述 12 个任务文件的当前 diff。
4. 先修复预测递归并运行同色双槽崩溃回归。
5. 再重构缓存键、空结果缓存和版本边沿。
6. 最后审查并提交普通块剩余计数。

