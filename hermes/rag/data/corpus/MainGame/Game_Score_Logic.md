# Game Score Logic（得分与连击）

本文对应 `Playbooks/game-score-logic.md`，聚焦“命中计分、combo 窗口、星级阈值与结算累计”。

## 1. 计分与连击规则

- 连击可由命中（`hit`）或窗内 merge 推进，窗口由 `shootIntervalMs` 控制（默认 5000ms，墙钟 `UtilsTime.TimeMilliseconds`）。
- 道具暂停主攻击期间（`IsCombatBlockedByGameplaySelection`）冻结连击窗：按墙钟推进 `_lastHitAtMs`，暂停时段不计入中断倒计时。
- 分数按命中即时结算；每次 `BlastBulletData` 命中都会推进 combo 并计算本次分数。
- 连击 UI：仅在连击推进边沿（窗内命中 `wasCombo` / 窗内 merge 成功）刷新 `ComboStarEffectView`（播 `Ani_ComboStarEffect_res` + 更新次数 + `MulTxt` 显示当前积分倍率）；不再播飘分 / 飘连击。
- merge 成功当下：若距上次连击时间戳仍在窗内，则 `combo +1` 并刷新时间戳；**merge 本身不加分**（`MulTxt` 按 `None` 档倍率展示）。
- 超窗外的 merge：不推进 combo、不重置 combo、不刷新时间戳。
- 同一 tick 内多次 merge：每次成功各计 1 次连击。
- 入口：`BlastGameController` → `BlastScorePureLogic.RegisterHit` / `RegisterMerge`。
- 命中 combo 的目标类型使用 `BlastBulletData.targetSpecialKind` 命中瞬间快照，不读取可能已被对象池复用的 `blockState.specialKind`。
- 基础分：`normalScore`；倍率表：`comboScoreBonusByComboCount`。
- 倍率选取（`ResolveHitScoreMultiplier`，与 `CalculateHitScore` 同口径）：
  - 先按目标类型读 `comboScoreBonusByComboCount[targetKind]`
  - 缺失回退 `BlastStackSpecialKind.None`
  - 倒序找首个 `comboCount >= Tier` 的 `Factor`
  - 得分：`RoundToInt(normalScore * Factor)`，最低 1
  - UI：`MulTxt` 显示 `x{Factor}`
- 命中来自 merge 槽位时，仍可按 `mergeSuccessScoreMultiplier` 加分（与 merge 连击推进无关）。

## 2. 结算顺序（关键）

`BlastGameController.Gameplay` combat tick 顺序：

1. `NotifyHitPositions(...)`
2. `RegisterHitCombos(...)`（命中计分 + 连击）
3. `RegisterMergeCombos(...)`（窗内 merge 只推进连击）
4. 结算 destroy score / merge 表现

该顺序保证同一波内先结算命中，再按 merge 次数推进连击。

## 3. 销毁事件粒度

- 普通块：每次销毁计 1 次事件。
- `Block2x2`：整组销毁计 1 次事件。
- `Gate`：一次 gate 销毁流程计 1 次事件。
- `Snake`：按实际移除 segment 逐个计事件。
- 同色 `Block2x2`（`block_big`）命中反馈：每次命中都打断当前 `res` 并从第 0 帧重播；同一 tick 命中同一视觉锚点时保留命中次数，逐次重启反馈，不在 UI 层去重。

## 4. 星级阈值

- 配置侧给倍率数组：`scoreMultipliers`。
- 运行时在 `LoadLevel` 后重算阈值：
  - `baseUnits = activeCandidates(amount 求和，跳过 lock)`
  - `baseScore = max(1, baseUnits * DataConfig.normalScore)`
  - `threshold[i] = ceil(baseScore * max(1, scoreMultipliers[i]))`
- 判星条件：`Score >= threshold[i]`。
- 进度条星标：`progress[i] = threshold[i] / threshold[last]`。
- 进度条填充：`BlastLevelProgressView` 按 `progress`（0~1）设置 `progressImg` 宽度，满宽度 `710` px（`SetSizeWithCurrentAnchors`）。
- 星标贴图：`InitStars` 按 `DifficultyLevel` 0/1/2 取 `difficultyDarkStars`（easy/hard/superhard），应用到 Stars（Progress1~3）的 Dark。

## 5. 共享纯逻辑与结算累计

- 计分纯逻辑：`Core/BlastScorePureLogic.cs`
  - `RegisterHit`
  - `RegisterMerge`
  - `CalculateHitScore`
- 结算累计纯逻辑：`Core/BlastLevelSettlementPureLogic.cs`
  - 胜负 streak
  - 关卡累计（BestCombo/Deaths/TimeSec/PowerUses）
  - `skillSmooth` 刷新

## 6. 验收要点

- 连续 hit 时 combo 递增；超窗后重置为 1。
- 窗内 merge 成功时 combo +1（不加分）；超窗外 merge 不影响 combo。
- 普通 hit 不加分，destroy 才加分。
- 同一 tick 内后续 destroy 使用更新后的 combo。
- `Block2x2 / Gate / Snake / Collectable` 分数与表现一致。

## 7. 类功能定位

| 类/文件 | 功能 | 路径 |
|---|---|---|
| `BlastGameController.Gameplay` | 命中反馈处理、combo 与得分调用顺序 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Gameplay.cs` |
| `BlastScorePureLogic` | 连击窗口、命中加分、窗内 merge 连击推进（不加分） | `Assets/GameModule/GameMain/Script/Core/BlastScorePureLogic.cs` |
| `BlastLevelSettlementPureLogic` | 关后累计统计、streak 与 skillSmooth 更新 | `Assets/GameModule/GameMain/Script/Core/BlastLevelSettlementPureLogic.cs` |
| `BlastHudView` | HUD 分数/进度显示；调试 `LoadLv` 走 `EnterGameLevelWithOverlay` 假切场景 | `Assets/GameModule/GameMain/Script/UI/BlastHudView.cs` |
| `ComboStarEffectView` | 连击推进提示（次数 + MulTxt 倍率；res 播完隐藏） | `Assets/GameModule/GameMain/Script/UI/ComboStarEffectView.cs` |

维护规则：计分口径变化时，先更新本表，确保“算法类 -> 入口类 -> 展示类”映射可查。
