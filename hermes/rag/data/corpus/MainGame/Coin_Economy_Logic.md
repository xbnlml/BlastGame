# Coin Economy Logic（金币通胀 / 动态定价）

## 摘要

- 公用类：`Assets/GameModule/Common/Script/Model/CoinEconomyUtil.cs`
- 现网 base 仍读 `BlastDataConfig`；调用方传入 base，经公用类放大后再发奖/扣款
- 对外**仅两个方法**：
  - `ScaleReward(base)` — 给金币（阶段通胀）
  - `ScaleCost(base)` — 花金币（动态定价 + 好数字取整）
- 阶段系数、日产、蚂蚁森林口子、取整均在类内私有，不对外暴露

## 已做

### 1. 发奖：阶段通胀

- 公式：`ScaleReward(base) = round(base × 阶段系数)`
- 阶段系数：按 `Profile.Level`（下一关进度）
  - 下标 = `(Level - 1) / 50`
  - 系数 = `1.0 + 下标 × 0.5`（1–50 → 1.0×，51–100 → 1.5×，可无限扩展）
- 已挂载调用点：
  - 通关奖：`BlastGameController.RollWinCoinReward`
  - Objective 临时币：`AddLevelTempCoin` 前

### 2. 花币：动态定价

- 日收入基准：
  - `daily_income = 蚂蚁森林日产 + economyDailyIncomeBase × 阶段系数`
  - `economyDailyIncomeBase`：`BlastDataConfig` 字段，默认 `3200`（asset 已写）
  - 蚂蚁森林日产：类内口子，**当前恒为 0**
- 倍率：`ratio = 持金 / daily_income`
  - `< 1` → `0.5`
  - `< 3` → `1.0`
  - `< 5` → `1.25`
  - 否则 → `1.5`
- 最终：`ScaleCost(base) = round_to_nice(base × 倍率)`
  - 好数字：500 / 800 / 1000 / 1200 / 1500 / 1800 / 2000 / 2200 / 2500 / 2800 / 3000 / 3500 / 4000 / 4500 / 5000
  - 超过 5000 按 500 步进
- 已挂载调用点（调用方 `ScaleCost(cfg.xxx)`）：
  - 标准道具购买价（`UIGamePropBuyView` / `CommonBuyBtn`）
  - 失败续命：`failReviveTempSlotCoinCost` 为数组，第 1 次 base=2000、第 2 次 base=4000（`ResolveFailReviveTempSlotCoinCost`），再 `ScaleCost`

### 3. 其它约定

- 不缩放存量持金；阶段切换只影响之后的发奖/扣款计算结果
- 不改现网 base 数值本身（道具 1800、复活 2100 等仍以配置为准）

## 未做（备注）

| 项 | 说明 |
|---|---|
| 蚂蚁森林整模块 | 仅日产口子返回 0；升级表 / 收集 / 8h 容量未做 |
| Pass / 签到 / 任务 / 礼包金币量 | 未挂 `ScaleReward`；后续发放处自行调用 |
| 商店礼包美元价 | 不调 |
| 文档示例基准价（道具 1000 等） | 不用；以现网配置为准 |

## 相关入口

- 类导航：`Doc/MainGame/module-index/common.md`（`CoinEconomyUtil`）
- 玩家数据总览：`Doc/MainGame/Player_Data_Logic.md`
- 胜负流程摘要：`Doc/MainGame/Gameplay_Flow_Logic.md`
