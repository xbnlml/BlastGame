# GameMain Sim / 规则索引

## 用途

从“攻击、特殊块、放置、队列、下落、补块、得分、动态难度”类提示词定位 Sim 入口与类职责。

| 关键词 | 首选入口 | 专题 |
|---|---|---|
| 攻击、命中、目标 | `BlastAttackSystem` | `Gameplay_Rules_Logic.md` |
| 战斗 tick | `BlastGameLogic.TickCombat` | `Gameplay_Rules_Logic.md` |
| 放置流、点击门控 | `BlastPlacementFlowState` | `Gameplay_Rules_Logic.md` |
| 合成、槽位状态 | `BlastStageController` / `TryMergeSlots` | `Gameplay_Rules_Logic.md` |
| 下落、补块、特殊结构 | `BlastEngine` | `Gameplay_Rules_Logic.md` |
| 队列、洗牌、初始队列 | `BlastQueueBuilder` / `BlastInitialQueueBuilder` | `Gameplay_Rules_Logic.md` |
| 难度应用 | `BlastDifficultyApplier` | `Blast_DynamicDifficulty.md` |
| 得分、连击 | `BlastScorePureLogic` | `Game_Score_Logic.md` |
| Key-Lock | `BlastKeyLockResolver` | `Gameplay_Rules_Logic.md` |

## 共享主链路

`Input → PlacementFlowState → TickCombat → Attack / KeyLock → Settle / Refill → Score`

## 核心类职责

| 类 / 文件 | 职责 | 协作者 |
|---|---|---|
| `BlastGameLogic` | 共享战斗 tick：KeyLock ×2 + PendingUnlock + UpdateAttacks | AttackSystem / KeyLockResolver |
| `BlastAttackSystem` | 目标选择、攻击推进、命中与特殊块击杀 | SpecialTargetSelector / GameLogic |
| `BlastAttackSystem.Targeting` | 特殊目标筛选与底行目标判定 | AttackSystem |
| `BlastAttackSystem.AttackOnce` | 单次射击分支 | AttackSystem |
| `BlastAttackSystem.State` | row sweep / 普通攻击队列快照（Bot clone 用） | AttackSystem / Bot |
| `BlastAttackSystem.SpecialBlocks` | 2x2 / Objective 等特殊块规则 | AttackSystem |
| `BlastPlacementFlowState` | 放置流纯数据状态机与输入解锁 | GatePolicy / Timing / Runtime Coordinator |
| `BlastEngine` | 下落、补块、特殊结构 settle | RigidGroups / BoardClosing |
| `BlastEngine.RigidGroups` | Gate/Block2x2 刚性组下落 | Engine |
| `BlastQueueBuilder` | 原始/难度队列构建与初始填充 | DifficultyApplier / InitialQueueBuilder |
| `BlastInitialQueueBuilder` | Runtime/Bot 共用初始 queue/pool 入口 | QueueBuilder |
| `BlastKeyLockResolver` | Key-Lock 配对与延迟解锁（Bot/Runtime 共用） | GameLogic |
| `BlastDifficultyApplier` | reverse / split-shuffle / overflow 难度策略 | QueueBuilder |
| `BlastGameStateTargetUnits` | 与 Target Cells 一致的可清除单位计数 | Controller / Bot |

## 放置流协作者

| 类 | 职责 |
|---|---|
| `BlastPlacementFlowGatePolicy` | 可否放置 / 阻塞策略 |
| `BlastPlacementFlowGateScheduler` | 门控时序调度 |
| `BlastPlacementFlowInputResolver` | 点击到放置意图 |
| `BlastPlacementFlowTiming` | 固定步时间参数 |
| `BlastDotNetRandom` | 随机源封装 |

## 代码目录

`Assets/GameModule/GameMain/Script/Sim/`
