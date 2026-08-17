# Game Model Logic（模型与共享数据）


## 数据模型职责

- `GameModelManager`：模型注册、初始化、查询与生命周期统一入口。
- `GameBaseModel`：基础生命周期与活动开关回调框架。
- `TimedActivityBaseModel`：时效活动时间数据解析与状态推进调度。
- 具体业务 Model（如 `GamePassModel`/`DailyDeliveryModel`/`GrandOpeningWeekModel`）只实现本模块业务，不接管公共状态机。

## 数据契约边界

- Model 层不做静默兜底兼容；配置缺失/状态异常应暴露为真实数据问题。
- UI 只消费 Model 输出，不在视图层补齐缺失数据或吞异常。
- Profile 初始化仅在合法初始化时机执行；进入稳定期后缺失字段按错误处理。

## 分层协作

- `Config/Profile -> Model Manager -> Runtime State/UI` 单向流动。
- 通行证加星等业务写入口保持集中（如 `TryAddWinStars`），事件仅用于通知刷新。
- 道具/奖励 Profile 写入入口应收口到 UserModule，不在各活动 Model 重复实现。

## 适用范围

说明 GameModule 数据模型的职责、来源和边界。具体字段以当前 C# 类型为准，本文只保留数据流。

## 1. 数据分层

```text
Config / Profile
  → loader / manager
  → runtime state
  → pure logic / UI / settlement
```

- Config：关卡、活动和静态配置。
- Profile：玩家持久化数据。
- Runtime state：当前一局可变状态。
- Pure logic：跨 Runtime/Bot 共享的计算。

## 2. GameMain 模型入口

| 数据 | 入口 | 用途 |
|---|---|---|
| 关卡配置 | `LevelProfileConfig` / `BlastLevelConfigParser` | 读取关卡 |
| 运行态 | `BlastGameState` | Board、Queue、Pool、分组 |
| 槽位 | `BlastSlotPiece` | 主槽和临时槽 |
| 候选 | `BlastCandidate` | Stage 输入 |
| 难度 | `BlastDifficultyContext` | 当前局难度 |
| 得分 | `BlastScorePureLogic` | 连击、星级、结算 |

## 3. 边界规则

- 配置和 Profile 不直接作为运行期可变状态。
- Runtime、Bot、Replay 共享纯逻辑，但各自负责输入和副作用。
- UI 读取状态，不持有玩法规则真源。
- 快照恢复必须深拷贝，禁止恢复后共享可变引用。

## 4. 代码定位

- 类型定义：`Assets/GameModule/GameMain/Script/Core/BlastTypes.cs`
- 关卡初始化：`BlastLevelLoader` / `BlastGameLevelSession`
- 难度：`BlastDifficultyContextFactory`
- 得分：`BlastScorePureLogic`
- 玩家数据：`Doc/MainGame/Player_Data_Logic.md`
