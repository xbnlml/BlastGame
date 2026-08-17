# Blast 动态关卡难度逻辑（独立文档）

本文描述动态难度在主游戏中的配置口径、计算链路与分层实现。

## 1. 结构分层（Data / Application / Runtime）

- Data：
  - `Runtime/BlastDynamicDifficultyBuildInputData.cs`
  - 承载关卡配置、`gameLevel`、cycle 等只读输入。
- Application（**唯一 Context 工厂**）：
  - `Core/BlastDifficultyContextFactory.cs` + `Core/BlastDifficultyEntryRequest.cs`
  - 底层：`BuildTierForced` / `BuildDynamic` / `BuildFromResolvedTier` / `BuildFromRecordedSnapshot` / `CloneReplayForcedDifficultyContext`
  - 进关路由：`BuildForEntry(BlastDifficultyEntryRequest)` — 模式 `ReplayClone | TierForced | NeutralEstimate | ProfileDynamic`
  - 内部 `AssembleFromTierConfig` / `AssembleCore` 统一字段赋值
  - Runtime、Bot、Workbench 禁止各自 `new BlastDifficultyContext` 拼装洗牌字段。
- Application（动态 tier 评估）：
  - `Runtime/BlastDynamicDifficultyCoordinator.cs`
  - 调用 `EvaluateForLevel` 得到 tier 后，委托 `BuildForEntry(ForProfileDynamic(...))`。
- Runtime Adapter：
  - `BlastGameLevelSession.BuildDifficultyContext(...)` → `BuildForEntry`（replay / forced）或 Coordinator（档案动态档）。
  - `BlastGameController.Loading` 仅桥接 Controller 状态。

## 2. 配置入口

- `BlastDataConfig` 关键字段：
  - `enableDynamicDifficulty`
  - `dynamicNeutralTier`
  - `dynamicSkillEma`
  - `dynamicStreakBoost`
  - `dynamicSkillDeathsWeight` / `dynamicSkillTimeSecWeight` / `dynamicSkillPowerUsesWeight`
  - `dynamicSkillDeathsRef` / `dynamicSkillTimeSecRef` / `dynamicSkillPowerUsesRef`

## 3. 状态来源

- 核心管理器：`Core/BlastDynamicDifficultyManager.cs`
- 运行态评估入口：`EvaluateForLevel(...)`
- 结算更新入口：`OnLevelSettled()`
- 持久化状态来自 `ProfileGameUser`：
  - `skillSmooth`
  - `winStreak` / `loseStreak`
  - `GameLevelDatas`

## 4. 默认值口径

- `skillSmooth` 初始值统一为 `1`。
- Runtime 首登初始化由 `UserMainData.ApplyInitialData(...)` 写入 `Profile.skillSmooth = 1`。
- Bot 本地战役态通过 `BlastSettlementProfileRecord` 默认值保持同口径。

## 5. 共享纯逻辑

- `Core/BlastDynamicDifficultyPureLogic.cs` 提供共享公式：
  - 开局评估（tier / dynamicOffset）
  - 结算 skillSmooth 更新（EMA）
  - cycle bonus 计算
- `Core/BlastDynamicDifficultyPureLogic.cs` 也提供共享档位映射：
  - `ResolveTierDifficultyConfig(MyStack, int tier)`：唯一取配入口，按 `tier(1~5)` 读取 `DynamicDifficultyConfigs[tier-1]`。
  - `ResolveDefaultDifficultyConfig(...)`：默认档位入口，等价于 `tier=3`。
- `BlastDynamicDifficultyManager` 与 Runtime coordinator 共用该逻辑，避免 Runtime/Bot 维护两套公式。

## 6. 运行时字段映射

- 关卡 series 难度五元组从 `MyStack.DynamicDifficultyConfigs[tier-1]` 读取。
- `StartDifficulty` 作为 `difficultyLoopOffset` 的基线输入，不会被动态难度回写。
- `levelDifficultyFactor` 仅存于 `BlastDataConfig`（资产默认 12）；经 `ReadLevelDifficultyFactor()` 直读，无运行时兜底；无 Context/Bot/Replay 透传。
- `cycleBonus` 当前固定为 `0`，`currentLevelCycle` 仍按 H5 口径映射。
- `EvaluateForLevel(...)` **仅计算 tier**（`skillSmooth + streak`）。
  - 按 `tier(1~5 -> index 0~4)` 读取 `MyStack.DynamicDifficultyConfigs`，落地：
    - `StartDifficulty` → `difficultyLoopOffset`
    - `ShuffleSplitCount` / `ShuffleSplitRatios` / `ShuffleOverflowFactor`
  - 读取入口：`BlastDynamicDifficultyPureLogic.ResolveTierDifficultyConfig(...)`。
  - 若配置列表为空、数量不足、对应档位为空，则返回空快照；导入器负责补齐 5 档。
  - 导入与批修：`LevelConfigImporter` / `Fix Generated Levels DynamicDifficultyConfigs (5)` 补齐 5 档；`NormalizeShuffleSplitRatiosCsv` 对齐比例长度。

## 7. 最终生效链路

### 7.1 自然动态档位（`EvaluateForLevel` 路径）

1. `EvaluateForLevel` / 档案 → `tier`（1~5）
2. `ResolveTierDifficultyConfig(stack, tier)` → 该档 `StartDifficulty` + `Shuffle*`
3. `difficultyLoopOffset = StartDifficulty`（+ `cycleBonus`，当前为 0）
4. `difficultyLevel =` 关卡 SO 字段 `DifficultyLevel`
5. 洗牌：`totalDifficultyIndex = difficultyLevel × levelDifficultyFactor + difficultyLoopOffset`

### 7.2 Forced 固定档位（HUD `DebugForcedTier`、Bot `forcedDynamicTier`）

入口：`BlastDifficultyContextFactory.BuildTierForced(level, forcedTier, cycle, gameLevel)`。

与 §7.1 相比，`dynamicTier` 固定为 `forcedTier`；其余字段（`difficultyLevel = SO DifficultyLevel`、`difficultyLoopOffset = StartDifficulty`、`currentLevelCycle = max(0, cycle-1)`）与自然进关同口径。

洗牌公式不变：`totalDifficultyIndex = difficultyLevel × levelDifficultyFactor + difficultyLoopOffset`。

### 7.3 Replay 回放（仅记录还原，无独立计算）

Runtime 读取 `load_level.action_note` 的 `dd*` token 后走 `BuildFromRecordedSnapshot`（或已有 context 时 `CloneReplayForcedDifficultyContext`）还原录制态。任一 token 缺失即拒绝 replay。

Bot 录制的 replay 也走这条路径，所以"人类 replay / 机器人 replay"在 Runtime 侧没有差别。

## 8. tier 计算（EvaluateForLevel 唯一职责）

- `baseTier = clamp(1 + floor(clamp01(skillSmooth) * 4), 1, 5)`
- `tier = clamp(baseTier + streakDelta, 1, 5)`
- `streakDelta` 由 `winStreak/loseStreak` 与 `dynamicStreakBoost` 计算。

## 9. 当前实现特性

- 开局评估要求最近对局样本数 `count >= 10`，否则返回中性档（无动态偏移），并沿用当前 `skillSmooth`。
- 样本不足阶段不会因缺省值回落到 `0`（默认值口径已统一为 `1`）。
- `OnLevelSettled()` 在结算后按 EMA 更新 `skillSmooth`：
  - `raw = dynamicSkillDeathsWeight * (avgDeaths / dynamicSkillDeathsRef) + dynamicSkillTimeSecWeight * (avgTimeSec / dynamicSkillTimeSecRef) + dynamicSkillPowerUsesWeight * (avgPowerUses / dynamicSkillPowerUsesRef)`
  - `skillNew = 1 - clamp01(raw)`
  - `skillSmooth = ema * old + (1-ema) * skillNew`

## 11. 方向语义

- `difficultyLoopOffset` 越大，最终难度索引通常越大、洗牌强度越高，通常更难。
- `difficultyLoopOffset` 越小，通常更简单。

## 12. 结论

- 动态难度不会修改关卡原始 `DifficultyLevel`。
- 动态难度不会覆盖或回写 `DynamicDifficultyConfigs` 内的 `StartDifficulty`。
- `StartDifficulty` 表示“基础起点”，不是最终运行时难度值。
动态难度只负责计算 `tier`，实际难度参数由关卡 `DynamicDifficultyConfigs` 档位决定。

## 13. 字段语义对照（2026-06）

| 标准名 | 当前代码字段 | 含义 |
|--------|--------------|------|
| `gameLevel` | `gameLevel` | 战役关卡序号 1,2,3… |
| `difficultyLevel` | `difficultyLevel` | SO `DifficultyLevel` 0/1/2 |
| `startDifficulty` | `startDifficulty` | 配置基线 |
| `difficultyLoopOffset` | `difficultyLoopOffset` | 洗牌公式加项；主路径 = `startDifficulty` |
- Campaign 与 Runtime 的 tier 计算公式一致，仅输入数据源不同；Bot 可通过 API 显式传入固定 tier 做同口径档位映射，Workbench range 批跑入口要求 tier 必须为 1~5。
