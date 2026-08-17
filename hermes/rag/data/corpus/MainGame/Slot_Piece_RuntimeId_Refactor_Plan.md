# SlotPiece 身份解耦交接计划

## 目标

彻底解耦 Slot 的“身份”和“位置”：

- `pieceRuntimeId`：唯一身份、Spine/动画所有权。
- 全局逻辑 `slotIndex`：当前数据位置。`[0, mainCount)` 为 Main，`[mainCount, +∞)` 为 Temp 逻辑位。
- Temp packed 座位、CellPool 下标：仅 `BlastSlotsView` 内部布局细节，禁止跨模块保存或用来定位动物。

最终所有异步 close / merge / fly 任务只按 `pieceRuntimeId` 找当前宿主；`slotIndex` 只用于读写逻辑数据。

## 用户复现问题

1. Temp 区有 3 只动物。
2. 其中 2 只合成到 Main；剩余 1 只压缩到 Temp 第 1 个表现座位。
3. 再触发 fail-revive，Main 的 3 只动物迁入 Temp。
4. 新补入后，Temp 第 1 只会被错误 close。

已观察到的日志：

```text
[Blast][TempSlotUiDiag] begin. moved=3, existingTempCount=1, renderTempCount=4
[Blast][TempSlotUiDiag] end. moved=3, flown=3, skippedInvalidUnit=0,
skippedSourceCell=0, skippedTempCell=0, skippedNoAnimal=0, skippedDetachFailed=0
```

上述日志说明飞入本身成功，不能证明 close 身份正确。

## 已确认的历史与现状

- `b879b364c`（2026-07-22）引入 Temp packed：`_tempPackedPieces`、`_tempPackedIndices` 与逻辑位→表现座位映射。
- `978c1298f`（2026-08-10）引入 fail-revive 表现、Closing 保座、A/B/C 延迟压缩，并新增 fail-revive 收集后按 `SourceSlotIndex` 升序排序：Main `3/4/5` → Temp `1/2/3`。
- `BlastSlotPiece` 当前没有稳定 ID；它会在 Stage 放入、Main 合成、fail-revive clone、回退 clone 等路径被重建。
- 当前实现混用了三种 `int`：Temp 逻辑位、packed 表现座位、全局 CellPool 下标。异步动画保存其中任意一个都会在压缩/补入后指向另一只动物。

## 已尝试、但必须在重构中删除的临时修补

这些改动尚未解决复现问题，不能作为最终架构保留：

- `BlastSlotsPieceVisualApplier.BeginTempCloseFly` 已增加 `expectedAnimalView`，close 执行时使用 `TryDetachSpecificAnimal`。
- `BlastSlotsView.TryDetachAnimalFromLogicSlot(...)` 返回转换后的可视索引，供 merge 回收 Cell。
- `BlastFailReviveTempSlots.TryFillTempSlots(...)` 目前尝试先压缩旧 Temp 再追加新单位。

重构完成后应删除跨模块的裸索引 capture/release/close API、旧兼容分支与索引双轨逻辑；不要在 ID 架构旁保留旧路径。

## 业务身份规则

| 场景 | `pieceRuntimeId` 规则 |
|---|---|
| Stage → Main 新放入 | 分配新 ID |
| Main → Temp fail-revive | 保留原 ID，更新 `slotIndex` |
| Temp packed 压缩 | 保留 ID，只移动布局座位 |
| Temp → Main 合成 | Main target ID 保留；参与合成的 Temp source IDs 在动画结束后注销 |
| 回退 / 回放 / 快照 clone | 保留 ID |
| Empty | ID 为 0 |

合成只在 Main 落结果；Temp 是材料区。合成计划必须保存：

```text
targetMainPieceRuntimeId
sourceTempPieceRuntimeIds[]
```

不得保存 Temp 表现座位作为身份。

## 目标运行时模型

```text
pieceRuntimeId
  └─ 当前宿主
       ├─ MainSlotCell
       ├─ TempSlotCell
       └─ DetachedAnimation（飞行 / merge / close 中）
```

建议 `BlastSlotsView` 持有唯一注册表：

```csharp
Dictionary<int, BlastSlotCellView> _cellByPieceId;
Dictionary<int, BlastStageAnimalView> _animalByPieceId;
Dictionary<int, int> _logicSlotByPieceId;
```

要求：活跃 ID 最多绑定一个 Cell 和一个 Spine。Cell 回池、Spine 入池、重载、场景切换、动画取消都必须同步清理或迁移注册表。

## 实施计划（替换式，无兼容层）

1. 为 `BlastSlotPiece` 增加 `runtimeId`，提供运行态唯一分配器。
2. 统一所有构造点：
   - `BlastStageController.CreateSlotPiece`：新生分配。
   - `BlastStageController.TryMergeSlots`：Main target 延续 target ID；Temp source ID 不进入新对象。
   - `BlastFailReviveTempSlots.CloneForTempSlot`：保留 source ID。
   - `BlastGameRollbackRuntime.CloneSlots`、`BlastGameController.Stage` 快照 clone、预测 clone：保留 ID。
3. `SlotsView` 建立并独占 `runtimeId → Cell/Spine/逻辑 slotIndex` 注册表；提供按 ID 查询、绑定、迁移、脱离、注销 API。
4. 改造 `BlastSlotCellView`：`AdoptAnimal`、detach、release、pool reset 都接收或清理 runtimeId，不允许只凭 owner slot index 判断动物身份。
5. 改造普通 Main/Temp 刷新：按 piece ID 查当前 Cell；packed 压缩仅更新同一 ID 的布局位置，禁止用新 piece 覆盖旧 Cell 的 Spine 身份。
6. 改造 fail-revive：迁移单元携带 source/target ID；飞入落地按 ID 绑定；二次续命追加新 ID 时不影响旧 Temp ID。
7. 改造 Temp→Main merge：按 source ID 捕获/脱离 Spine，按 target Main ID 找结果 Cell；动画结束注销 source IDs。
8. 改造 close/攻击：任务保存 ID（可附加预期 Spine）；执行时按 ID 验证当前宿主与 Spine，不符即取消，禁止退化为按 Temp 座位 detach。
9. 删除旧逻辑：所有跨模块 `TryGetTempSlotCell`、CellPool 下标、逻辑索引直接回收 Cell、Temp 座位直接 close 等身份入口全部删除；索引转换只留在 `SlotsView` 私有布局代码。
10. 添加最小断言/诊断：ID 唯一绑定、Cell 回池无残留注册、packed 前后同 ID 的 Spine 不变；日志统一输出 ID + 逻辑 slotIndex + 宿主。

## 验收

1. Main `5/4/3` → Temp `1/2/3`：ID 不变，Spine 不重建。
2. Temp 三只合成两只、剩余一只压缩到首位：source IDs 注销，幸存 Temp ID/Spine 不变，Main target ID 保留。
3. 在步骤 2 后二次 fail-revive 补入三只，再触发攻击/close：close 只命中请求 ID，首位不被旧任务关闭。
4. 回退、重载、场景切换、动画取消后：注册表只含当前存活 ID 或为空，无旧 Spine/回调残留。

## 工作区注意事项

工作区在交接时已有多处未提交修改，且不全属于本任务。不要 `reset`、`checkout` 或批量还原。与本次相关的现存改动包括：

- `Runtime/BlastPowerUpMagicBox.cs`
- `Runtime/BlastSlotsCloseFlyController.cs`
- `Runtime/BlastSlotsPieceVisualApplier.cs`
- `UI/BlastSlotsView.cs`
- `UI/BlastUiAnimExecutor.cs`
- `Doc/MainGame/Gameplay_Flow_Logic.md`

另有用户/其他任务改动：`BlastGameViewPresenter.cs`、`BlastSlotCellDetachedCloseAnim.cs`、`UIGameMainEffectLayerController.cs`、`BlastSlotCellView.cs` 等；先用 `git diff` 分辨归属。
