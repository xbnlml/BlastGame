# 动态难度机制说明

## 1. 机制

动态难度每局结算后根据玩家最近最高 10 个关卡的累计表现更新 `tier`（1~5），下一局开局前锁定该 `tier`。客户端先用 `tier` 读取 `DynamicDifficultyConfigs[tier-1]` 的同档位配置，再按运行分支决定是否叠加 `dynamicOffset`；不修改关卡原始 `DifficultyLevel`。

## 2. 主公式

```
tier = clamp(baseTier + streakDelta, 1, 5)
difficultyLoopOffset = ResolveTierDifficultyConfig(stack, tier).StartDifficulty
totalDifficultyIndex = DifficultyLevel × levelDifficultyFactor + difficultyLoopOffset
```

其中：

```
startDifficulty / Shuffle* = ResolveTierDifficultyConfig(stack, tier)
levelDifficultyFactor = BlastDataConfig（默认 12）
baseTier      = 1 + floor(clamp01(skillSmooth) * 4)
skillSmooth   = dynamicSkillEma * skillSmooth_old + (1 - dynamicSkillEma) * (1 - clamp01(0.45*(avgD/3) + 0.35*(avgT/120) + 0.20*(avgP/5)))
avgD          = 最高 10 个关卡累计 deaths 的关卡平均值
avgT          = 最高 10 个关卡累计 timeSec 的关卡平均值
avgP          = 最高 10 个关卡累计 powerUses 的关卡平均值
```

当前客户端实现中的字段映射（[`BlastDifficultyContext`](../../Assets/GameModule/GameMain/Script/Core/BlastTypes.cs)）：

- `gameLevel`：战役关卡序号（1,2,3…）；Replay token `ddGameLevel`（兼容 `ddLevel`）
- `difficultyLevel`：关卡 SO `DifficultyLevel`（0/1/2）；Replay token `ddDifficultyLevel`（兼容 `ddLevelDifficultyLevel`）
- `startDifficulty` 来源于 `ResolveTierDifficultyConfig(stack, resolvedTier)` 对应档位的 `StartDifficulty`
- `resolvedTier` 来源于服务器/档案数据按本文公式计算；测试入口可强制指定 tier；未指定时使用 `dynamicNeutralTier`（当前为 3）
- `difficultyLoopOffset` 不回写 `MyStack`，只写入运行时 `BlastDifficultyContext`（Context 字段名，主路径等于 `startDifficulty`）
- Context 组装唯一入口：[`BlastDifficultyContextFactory.BuildForEntry`](../../Assets/GameModule/GameMain/Script/Core/BlastDifficultyContextFactory.cs) + [`BlastDifficultyEntryRequest`](../../Assets/GameModule/GameMain/Script/Core/BlastDifficultyEntryRequest.cs)
- 方向语义：`difficultyLoopOffset` 越大，最终 `totalDifficultyIndex` 越大，队列洗牌强度通常越高；通常表示更难。`difficultyLoopOffset` 越小则通常更简单。

`streakDelta` 规则：

- `boost = dynamicStreakBoost`
- 连胜：
  - `winStreak >= 4 => +boost`
  - `winStreak >= 2 => +round(0.5 * boost)`
- 连败：
  - `loseStreak >= 3 => -2 * boost`
  - `loseStreak >= 2 => -boost`
- 其他 => `0`

## 3. 客户端需要处理

### 3.1 开局前

1. 加载动态难度状态。
2. 读取最高 10 个关卡累计记录，计算 `skillSmooth -> baseTier -> streakDelta -> tier`。
3. 根据 `tier` 读取对应档位配置，得到本局同档位难度参数。
4. 锁定本局 `tier`，本局内不再变化（但允许相邻两局跨多档变化）。

### 3.2 结算时

1. 按关卡号写入或更新 `GameLevelDatas[level]`：累计 `deaths`、`timeSec`、`powerUses`；超过 10 个关卡记录时删除最小关卡号，保留最高 10 个关卡。
2. 使用结算态 `won` 更新 streak（`winStreak/loseStreak`）。
3. 更新 `skillSmooth` 并持久化。

### 3.3 客户端配置参数

- `enableDynamicDifficulty`：总开关；关闭时不应用动态难度。
- `dynamicNeutralTier`：中性档位，通常为 3。
- `dynamicSkillEma`：技术分平滑系数（越大越稳、响应越慢）。
- `dynamicStreakBoost`：连胜/连败修正强度。

### 3.4 当前客户端落地链路

1. `LevelProfileConfig.Stack` 暴露内联 `MyStack` 配置。
2. 开局加载时先确定 `resolvedTier`，再通过 `BlastDynamicDifficultyPureLogic.ResolveTierDifficultyConfig(stack, resolvedTier)` 读取同档位 `StartDifficulty` / `ShuffleSplit*` / `ShuffleOverflowFactor`；全局 scale 仅在公式内读取 `BlastDataConfig`。
3. `EvaluateForLevel(...)` 仅算 `tier`；`difficultyLoopOffset` 与同档 `Shuffle*` 均由 `ResolveTierDifficultyConfig(stack, tier)` 读取。
4. 队列难度索引：`DifficultyLevel × levelDifficultyFactor + difficultyLoopOffset`。

结论：

- 动态难度不会修改关卡原始 `DifficultyLevel`
- 动态难度不会回写 `DynamicDifficultyConfigs` 内的 `StartDifficulty`
- 动态难度只影响本局运行时的 `difficultyLoopOffset`
- 一般可直接按“`difficultyLoopOffset` 越大越难、越小越简单”理解导出结果；但若 `dynamicOffset` 因取整落成 `0`，也可能出现 `tier` 已变化而落地难度看起来未变。
- H5 口径补充：当前 H5 的 `PACK_LEVEL_COUNT` 未列出 `funnel b`，因此在该包下 `currentLevelCycle` 会按 H5 规则回落为 `0`，不会因为连续通关而在 Runtime/Bot 里持续累加。

## 4. 服务器需要记录

如果动态难度状态放在服务器，记录以下字段。

- `GameLevelDatas`：最多保留 10 个关卡号记录；线性推进时删除最小关卡号，保留最高 10 个关卡。
  - `deaths`：该关累计死亡压力指标（当前实现是失败/续命相关计数）。
  - `timeSec`：该关累计总耗时（秒）。
  - `powerUses`：该关累计道具使用次数。
- `winStreak`：当前连续胜利局数。
- `loseStreak`：当前连续失败局数。
- `skillSmooth`：平滑后的技术分（0~1）。

说明：

- `won` 不进入 `records`，只作为每局结算事件字段用于更新 `winStreak/loseStreak`。


