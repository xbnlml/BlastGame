# Play On Offer / FailOffer 逻辑

失败续命板上的现金礼包（Play On Offer）专题真源。主流程编排摘要见 [`Gameplay_Flow_Logic.md`](Gameplay_Flow_Logic.md)。

## 1. 概述

玩家在关卡失败且可续命时，`UIGameContinueView` 可并排展示：

- **金币复活**：扣金币腾槽续命
- **复活礼包（FailOffer）**：IAP，复活 + 配置奖励（金币/道具）

有活动展示时，**仅点 close** 记拒绝；走金币复活不记拒绝。

## 2. 触发门控

配置表：`PlayOnOfferConfig`（`ConfigName` → `ConfigValue`）

| 键 | 默认 | 含义 |
|---|---|---|
| `ScoreProbability` | 0.5 | 关内目标格进度阈值 |
| `ChangeFaleOfferAgreeCount` | 3 | 升档所需购买次数 |
| `ChangeFaleOfferDisAgreeCount` | 10 | 相对默认降 1 档所需累计拒绝次数 |
| `ChangeFaleOfferDoubleDisAgreeCount` | 20 | 再降 1 档额外所需拒绝次数（累计阈值 = 10+20=30） |
| `DownshiftDayNeed` | 7 | 时间降档所需天数 |

写死规则：

- 不限难度、不限等级、无随机弹出概率
- 进度 = `(total - remaining) / total`，与 HUD Target Cells 同源：`InitialTargetUnitTotal`、`RemainingTargetUnitsWithReserves`
- 进度 **>= ScoreProbability** 才可能弹

入口：`FailOfferModel.IsUnlocked()`（通过后对齐档位、时间降档、解析 awards 并 **log**）。

## 3. 付费分层与默认档

数据源：`ProfileGameUser.CurrentPurchaseLayer`（由 `UserModuleManager.RefreshCurrentPurchaseLayer` 按 `RealPaidTotal` 写入）。

配置：`UserGamePurchaseLayer`（`LayerId` / `PurchaseMin` / `PurchaseMax` / `DefaultOfferId`）。

- **默认档** = 当前分层的 `DefaultOfferId`
- FailOffer **不再**存独立的 `CurrentPurchaseLayer`
- 分层 **id 升高**（支付成功刷新分层后）：`FailOfferModel.OnPurchaseLayerRaised` 抬底 `offer = max(current, newDefault)` 且不超过 newDefault，**不清** Agree/DisAgree
- 展示时若 `CurrentFailOfferId > default`，压回 default

## 4. 存档 `ProfileGameFailOffer`

| 字段 | 默认 | 含义 |
|---|---|---|
| `CurrentFailOfferId` | 0 | 当前 Offer 档 **0–4** |
| `CurrentFailOfferAgreeCount` | 0 | 当前回弹购买计数 |
| `CurrentFailOfferDisAgreeCount` | 0 | 当前累计拒绝次数（降档不清零） |
| `HistoryFailOfferAgressState` | `{}` | 各 offerId 历史同意次数；永不清空 |
| `HistoryFailOfferDisAgressState` | `{}` | 各 offerId 历史拒绝次数；永不清空 |

支付商品 id：`FailOfferID = 2001 + CurrentFailOfferId`。

相关时间：

- 上次支付：`ProfileShop.LastPurchaseTime`（所有支付成功在 `PurchaseModule.PurchaseEnd` 写入）
- 首次安装：`ProfileCommon.InstalledAt`（0 元党时间降档锚点）

## 5. 首次对齐

历史 Agree/DisAgree 皆空且两计数为 0、且 `CurrentFailOfferId == 0` → 视为首次，写入 `defaultOfferId`。

## 6. 三入口数据变化

### A. `OnOfferPurchased`（买成功）

1. HistoryAgree++；发奖
2. `AgreeCount += 1`
3. `AgreeCount >= ChangeFaleOfferAgreeCount` → `offer = min(cur+1, default)`，**一律** `Agree=0`、`DisAgree=0`（已在最大档也清）
4. 未满次数：不升档，DisAgree 不动

### B. `OnOfferRejected`（活动展示中点 close）

1. HistoryDisAgree++；`DisAgreeCount += 1`（不改 Agree）
2. 地板：`floorId = max(0, default - 2)`；`current <= floorId` → 不降
3. 否则：
   - `offset = default - current`
   - `offset == 0` 且 `DisAgree >= 10` → 降 1
   - `offset == 1` 且 `DisAgree >= 30` → 再降 1
4. 降档时：**不清** DisAgree；档位变了则 Agree=0

### C. `IsUnlocked` 内时间降档（门控与对齐后、展示前）

1. 仅 `current == default` 且高于地板
2. 锚点：`LastPurchaseTime > 0` 用它，否则 `InstalledAt`
3. 天数 `>= DownshiftDayNeed` → 降 1（不低于地板）
4. **确实降档**才清 Agree+DisAgree；未降不动

## 7. 礼包奖励

配置：`PlayOnOfferPackageConfig.awards`

解析：`RewardStringParser.TryParseRewards`

- 按逗号分段
- `id:count`：固定奖励
- `id|id|...:count`：从池中 **抽 1 个 id**，数量为 count

发奖：`1001` → `AddCoinAndSync`；已知道具枚举 → `AddPowerUpAndSync`；其它 → `TryAddProfileItem`。

## 8. 类导航

| 类 | 职责 | 路径 |
|---|---|---|
| `FailOfferModel` | 门控、三入口升降、发奖 | `Assets/GameModule/FailOffer/Scripts/FailOfferModel.cs` |
| `UIGameContinueView` | 续命弹板；仅 close 记拒绝 | `Assets/GameModule/GameMain/Script/UI/UIGameContinueView.cs` |
| `UserModuleManager` | 付费分层刷新 | `Assets/GameModule/UserModule/Script/Runtime/UserModuleManager.cs` |
| `PurchaseModule` | 支付成功写 LastPurchaseTime / 刷新分层后抬 FailOffer 底 | `Assets/Module/Purchase/Scripts/PurchaseModule.cs` |
| `ProfileGameFailOffer` | 存档 | `Assets/GameModule/ServerProfile/ProfileGameFailOfferModule/ProfileGameFailOffer.cs` |
| `PlayOnOfferConfig` / Package | 进度阈值与升降档配置 / 礼包 | `Assets/GameModule/GameDataConfig/Config/PlayOnOffer/` |
| `UserGamePurchaseLayer` | 付费分层表 | `Assets/GameModule/GameDataConfig/Config/UserGamePurchaseLayer/` |
