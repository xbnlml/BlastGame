# Game Pass Logic

## UI 资源归属整理

- GamePass 使用通用 `SplitAtlases` 工具整理 UI 纹理；完整规则和操作说明见 `Doc/Tools/SplitAtlases_Usage.md`。

## 摘要

- 通行证数据由 `GamePassModel` 管理，入口通过 `GameModelManager.Instance.GetModel<GamePassModel>()` 获取。
- 过关加星采用直调：`EnterWinState` 直接调用 `GamePassModel.TryAddWinStars(star)`。
- 事件可用于 UI 刷新，但不承担通行证数据写入。
- `GamePassModel.HasUnlockFrame(frameId)` 是 Chefs Pass 头像框解锁查询入口；头像框配置的 `Unlock_Condition=ChefsPass` 时由个人资料模型调用。

## 配置来源

- 期数配置：`Assets/Module/Chefs_Pass/Config/Data/chefs_pass_config.json`
  - `PassID`：赛季标识
  - `Time_Anchor` + `Time_Duration`：赛季时间窗
  - `RewardsID`：奖励表映射键
- 奖励配置：`Assets/Module/Chefs_Pass/Config/Data/chefs_pass_reward.json`
  - `Node=0..30`：常规等级档
  - `Node=9999`：30 级后循环奖励档

## Profile 映射

- 类型：`ProfileGamePassData`
- 字段：
  - `PassId`
  - `PassEndTime`
  - `PassCollectStar`
  - `PassFreeRewardState`
  - `PassPayedRewardState`
  - `PassIsPayed`

## 赛季初始化与重置

- 活动开启时：
  - 若 `ProfileGamePassData` 为空，先创建并回写 `ProfileGameModule.GamePassData`。
  - 在 `ResolveTimeData(nowSeconds, out result)` 中从 `Chefs_Pass_Config` 选取当前 season，并回填给 `TimedActivityBaseModel`。
  - 若 `PassId + PassEndTime` 与当前 season 不一致，重置本期进度与领奖状态。
- season 选择口径：
  - 仅使用“当前进行中”的 season，不预取下赛季。
  - 若有多个进行中配置，取 `Time_Anchor` 更晚的一条作为当前期。
  - 本期结束后会重评估并自动挂到下一期开启时间（若存在下一期）。
- 重置内容：
  - `PassCollectStar = 0`
  - `PassFreeRewardState = new ProfileDict<int,bool>()`
  - `PassPayedRewardState = new ProfileDict<int,bool>()`
  - `PassIsPayed = false`

## 过关加星

- 入口：`Assets/GameModule/GameMain/Script/Runtime/BlastGameController.State.cs` 的 `EnterWinState`。
- 逻辑：
  - 结算出 `star` 后，直调 `GamePassModel.TryAddWinStars(star)`。
  - `GamePassModel` 内部做活动开启校验、累加 `PassCollectStar`、并触发 Profile 同步。

## 进度区间口径（首页进度条）

- `PassCollectStar` 是累计星数。
- UI 展示区间使用“当前节点差值”且始终跟随最新累计星数（不再因未领奖停留在旧档满格）：
  - `segmentCurrent = PassCollectStar - previousNode.Stars_Demand`
  - `segmentTotal = currentNode.Stars_Demand - previousNode.Stars_Demand`
- 新赛季 0 星时若 `Node 0` 的 `Stars_Demand=0`，首页会直接显示下一档区间（例如 `0/1`）。
- 满级（Node 30）后：
  - 未付费：首页显示 `MAX` + 满条（free 终态）。
  - 已付费且有 9999 配置：按 9999 的 `Stars_Demand` 继续显示循环区间进度（从 free `MAX` 可切换到循环进度）。

## 首页角标口径（可领未领数量）

- 首页角标不再表示进度，而是表示“可领未领的奖励格子数”。
- 计数规则：
  - 普通节点：达成阈值后，若免费或付费奖励中任意一格未领，则该节点计 `+1`；同一普通节点最多只计一次。
  - 普通节点付费奖励仅在 `PassIsPayed=true` 时参与统计；未购买时只看免费格。
  - 循环奖励（`Node=9999`）仅在 `PassIsPayed=true` 时生效，并按循环领奖 key（`maxLevelNode + 1 .. maxCyclicKey`）逐份统计；每个未领取 key 计 `+1`。

## 奖励领取

- 免费领取：`TryClaimFreeReward(node)`
  - 条件：活动开启、达成 `Stars_Demand`、未领取。
  - 状态：`PassFreeRewardState[node] = true`。
- 付费领取：`TryClaimPaidReward(node)`
  - 条件：活动开启、`PassIsPayed=true`、达成 `Stars_Demand`、未领取。
  - 状态：`PassPayedRewardState[node] = true`。

## 满级节点与循环奖励（Node=9999）

- 满级阈值：从当前期奖励配置中动态取“最大普通节点（排除 `9999`）”的 `Stars_Demand`，不写死为 30。
- 循环阈值：`Node=9999` 的 `Stars_Demand`。
- 可领次数：`(PassCollectStar - maxLevelDemand) / cyclicDemand`。
- 领取状态键：
  - 使用 `PassPayedRewardState[maxLevelNode + k]` 表示第 `k` 次循环奖励是否已领。
  - 奖励内容始终读取 `Node=9999` 的 `Pass_Reward`。

## 首页接线

- `GameBaseModel` 提供活动共性状态 `IsActivityShow` / `ActivityUnlockLevel` / `IsActivityLevelLocked` / `IsActivityOpen`；`GamePassModel` 在此基础上维护 Pass 自己的进度与节点只读字段。
- `UIHomeLevelPass` 直接读取 `GamePassModel` 只读状态并订阅 `StateChanged` 刷新，不写 Profile / Model。
- `UIHomeLevelView` 仅作为容器，不再拼装 pass 业务数据。
- 首页展示口径（`Activity_Config.Chefs_Pass`）：
  - `Visibility_Condition` 未达标（如 `<15`）：隐藏整个 pass 模块。
  - `Show_Condition` 未达标且已可见（如 `15~34`）：显示模块并提示解锁等级（如 `Level 35`）。
  - 达到 `Show_Condition`（如 `>=35`）但赛季未开启：显示 `Coming Soon`。
  - 达到 `Show_Condition` 且赛季进行中：显示正常通行证节点锁态文案。

## 付费购买接线（CommonBuyBtn + 模块回调）

- 按“通用点击 + 模块刷新”分层：
  - 点击购买：`UIPassBuyView` 通过 `CommonBuyBtn.SetBuyData(...)` 配置购买参数，由 `CommonBuyBtn` 统一调用 `PurchaseSystem.Instance.Purchase(...)`。
  - 回调注册：`GamePassModel.AddActivityEvent()` 内注册 `PurchaseSystem.Instance.Register(PurchaseType.GamePass, OnPurchaseSuccess, null)`。
  - 回调解绑：`GamePassModel.RemoveActivityEvent()` 内执行 `PurchaseSystem.Instance.UnRegister(PurchaseType.GamePass)`。
  - 数据刷新：`GamePassModel.OnPurchaseSuccess(...)` 内按 `purchaseId` 更新模块状态（如 `SetPassPurchased(true)`），再走模块既有 `StateChanged` 刷新链路。
- 约束：
  - `CommonBuyBtn` 不承载 `GamePass` 业务状态变更。
  - `GamePassModel` 不处理按钮点击交互细节，只处理支付结果与模块数据收口。
  - 后续新增购买入口沿用同一模式：Common 层负责触发支付，模块 Model 负责结果落地。

### 首页奖励显隐规则

- 未解锁（`IsNextNodeLocked=true`）：
  - `PassLockRoot` 显示；
  - `PassLockText` 显示解锁等级；
  - `RewardItemFree` 与 `TwoItem` 下 `PayRewardItem` / `PayRewardItem_1` 都不显示。
- 已解锁且未购买（`IsNextNodeLocked=false && IsPaid=false`）：
  - 奖励内容按当前首页展示节点配置解析（首 token `itemId:count`）；
  - 显示 `RewardItemFree`；
  - 隐藏 `TwoItem` 下 `PayRewardItem` / `PayRewardItem_1`。
- 已解锁且已购买（`IsNextNodeLocked=false && IsPaid=true`）：
  - 奖励内容按当前首页展示节点配置解析；
  - 显示 `RewardItemFree`，并对 `TwoItem` 下 `PayRewardItem` / `PayRewardItem_1` 同步调用原付费格 `Show`（同份 `PaidData`）。

### 首页奖励卡片展示口径

- 首页常态下，奖励卡片始终显示“当前最新展示节点”对应的奖励内容，不再因为存在更早的可领未领奖励而回退到旧节点。
- 动画态若需要先展示旧快照再过渡到新节点，属于首页返回演出链路的临时显示，不改变常态展示口径。

## 首页返回演出链路（登录基线 + 关卡返回）

- `UIHomeLevelPass.Init(true)`：首页模式；首帧刷新后保存展示快照（基线）。
- `UIHomeLevelPass.Init(false)`：通行证主界面复用，只做直接刷新，不参与首页返回演出。
- `UIHomeLevelView.TryOpenGameMainIfHealthy()`：进关前标记“待返回差异判断”。
- 关卡返回首页时：仅当存在返回标记且 `PassCollectStar` 相对基线增加时，由 `UIHomeLevelPass` 触发收星/进度回放；动画参数读 `GameConst`，UI 不改 Profile。
