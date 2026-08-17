# Stage Animal 动画播放主流程


## 职责边界

- `BlastStagePlacementAnim`：只负责放置表现调度，不拥有放置结果真相。
- `BlastSlotCellView.AdoptAnimal`：Stage→Slot 动物接管唯一入口，负责实例所有权转移。
- `BlastSlotsPieceVisualApplier`：只按状态边沿驱动动画，不改数据状态机。
- `BlastStageAnimalView` / `BlastStageAnimalPool`：承载与复用 Stage/Slot 共用动物视觉实例。

## 协作口径

- 数据先于表现：Controller/Sim 先完成候选与目标槽位规划，UI 后执行飞行/落位/合并表现。
- 状态驱动单向：`FlyingIn/Merging/Closing` 进入由规则层决定，UI 不从动画回调反推状态。
- 同一状态边沿只触发一次；逐帧刷新不能重复重置同名动画。

## 生命周期与对象池

- Stage 与 Slot 动物采用“单实例迁移”口径：detach -> fly -> adopt，不走重建替代迁移。
- 动物实例回收仅发生在合并/关闭最终收口阶段；飞行与中间过渡不得提前回收。
- 切场/重载时统一清理 tween、回调、连线与临时飞行对象，避免跨局残留引用。

## 适用范围

说明 Stage 候选动物如何进入 Slot、如何由状态驱动表现以及如何与对象池协作。具体动画名、资源路径和调试日志不在本文维护。

## 1. 主链路

```text
Stage click
  → placement validation
  → data placement / target slot
  → detach AnimalView
  → fly to Slot
  → adopt into SlotCell
  → state transition / merge
```

- 数据层先完成候选、槽位和目标关系。
- UI 层只执行已经确定的飞行、合成和关闭表现。
- 动画结束不能决定数据是否成功；数据成功后即使表现失败也必须继续同步。
- detached 动物的 close/merge 表现即使被取消，也必须在 finally/取消分支回收到 StageAnimalPool，不能只清空 View 引用。
- `merge` 仅由 `BlastStagePlacementAnim.PlayMergeGroupToTargetAsync` 播放；`EnterMergingVisualState` 只同步 UI 状态，禁止再次启动同一 Spine 动画。

## 2. 状态驱动

- Stage/Slot 视觉由当前数据状态和状态边沿驱动。
- `FlyingIn` 只表示落位过渡，收口后才参与攻击或合成。
- `Merging`、`Closing` 的进入由 Sim/Runtime 状态机决定，UI 不从动画回调反推状态。
- 同一状态边沿只播放一次，逐帧刷新不能重复触发动画。

## 3. 对象池与生命周期

- 出池：绑定当前颜色、形态、状态和所属 Cell。
- 飞行：AnimalView 从 StageCell 脱离；普通挂 `SotsViewUp`；磁铁道具挂弹板 `MagnetFlyParent`（盖过 Prop1 挖洞遮罩），`SetAsLastSibling`。
- merge：参与体 Spine 挂 `SotsViewUp`；**保留位**进度条+数字按抬层前 sibling 先后临时抬到 `SotsViewUp`（`BeginMergeTargetChromeOnEffectLayer`），收口按原 parent/sibling/锚点还原（`EndMergeTargetChromeEffectLayer`）。
- 落地：由 SlotCell adopt，之后由 Slot 视图管理（即回原层级）。
- 回收：清理 tween、回调、连线和 Spine 状态。
- 重载、回退、退出：统一释放所有 Stage/Slot 动物和临时飞行对象。
- Stage 候选全部放置完成后，玩法区域可按 `BlastGameplayAreaSpeed` 加速；该倍率只覆盖 Board/攻击/Slot 玩法表现，不覆盖弹板出现动画或其他场外 UI。判定以 `Candidates` 无激活项为准，不以 Slot 是否已满为准。

新旧 Piece、Animal、Cell 的所有权必须分离，不能按 slot index 判断对象身份。

## 3.1 2to3 飞行配置与道具路径

- 普通前排 2to3：`stageAnimal2To3FlySettings`（Gravity / FixedDuration / TimeProgressEase）+ Spine `stageAnimalAnim2To3` 静态 TimeScale。
- 磁铁等道具 2to3：`stageAnimal2To3FlySettings2`（Inspector：`Prop Use UI` → `磁铁飞行`）；计划 `UseProp2To3FlySettings` → `PlayOnceWithTargetDuration("2to3", FixedDuration)`，Spine TimeScale = `baseAnim2To3 / FixedDuration`；飞层=`PropUseUi.MagnetFlyParent`，落地 Adopt + `ReleaseHeldEffectClose`。
- 抛物线反解只保证任意起终点在 FixedDuration 内飞完；不是按距离自动改速。

## 3.2 Stage 布局与后排动物缩放

- 排高：`BlastStageView` 读 `BlastUIRuntimeConfig` Stage 栏（`stageCellSize` / `stageRowGap` / `stageColGap` / `stageHiddenRowsExtraGap` / `stageMaxRows`）。`y = -displayRow * (cellSize+rowGap)`；超过 `stageMaxRows` 的隐藏行再加 `stageHiddenRowsExtraGap`。
- 后排（`displayRow>0`，含显示 2/3 与隐藏 4/5）缩放动物 `Root` 与 Lock 视觉为 `stageBackRowAnimalScale`，不改 cell 排距/点击区。Link 线条仍挂 `effectsRoot`，线宽与端点 Mark 不乘该倍率；端点按忽略动物 Root 缩放后的骨骼世界坐标取样，避免后排缩小时线被拉向中心。
- 还原到 1：1to2 进前排、魔棒落到前排、道具 2to3 飞 Slot。时长/曲线为 `stageBackRowScaleRestoreDuration` / `stageBackRowScaleRestoreCurve`（默认对齐 1to2 `FixedDuration` + Linear）。道具 2to3 飞行中先插值到 1，再乘 `magnet2To3FlyScaleCurve`；落地 snap 为 1。后排互推（如 3→2）不还原。

## 4. 代码入口

| 问题 | 入口 |
|---|---|
| Stage 点击与数据放置 | `BlastGameController.Stage` |
| 放置流门控 | `BlastPlacementFlowCoordinator` |
| 飞行动画 | `BlastStagePlacementAnim` |
| 动物实例 | `BlastStageAnimalView` / `BlastStageAnimalPool` |
| Stage 展示 | `BlastStageView` / `BlastStageCellView` |
| Slot 接管 | `BlastSlotsView` / `BlastSlotCellView` |
| 状态驱动动画 | `BlastSlotsPieceVisualApplier` |
| 三大区域刷新 | `BlastGameViewPresenter.RefreshRuntimeViews` |
| 普通/道具 2to3 飞配置 | `BlastUIRuntimeConfig.ResolveStageAnimal2To3FlySettings(useProp)` |

## 5. 排查顺序

1. 先确认数据是否成功放置和绑定目标槽位。
2. 再确认 AnimalView 是否正确 detach / adopt。
3. 再检查状态边沿是否只触发一次。
4. 最后检查 tween、对象池和连线清理。
5. 磁铁早开火：核对 Put 后是否立刻有 PendingAttackSlots，以及 FlyingIn 是否含 PropShow 延迟。
