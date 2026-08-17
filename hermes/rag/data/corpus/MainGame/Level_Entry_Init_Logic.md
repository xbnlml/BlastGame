# Level Entry Init Logic（关卡进入初始化）


## 入口类职责

| 类/文件 | 功能 |
|---|---|
| `BlastLevelEntry` | 进关/下一关/重开/跳关统一入口编排 |
| `BlastGameController.Loading` | 加载流程调度与运行态装配 |
| `BlastLevelLoader` | 配置转运行态（state/slots/candidates/queue） |
| `BlastLevelConfigParser` | 关卡资源解析与配置读取 |
| `BlastDifficultyContextFactory` | Runtime/Bot/Replay 难度上下文统一构建 |

## Runtime/Bot 分层边界

- Runtime 主链路读取 `LevelProfileConfig`，Bot 在边界层做数据适配，不复制初始化规则。
- 加载阶段只解析一次配置并复用，避免重复解析导致口径漂移。
- 初始化失败必须回退到安全态，禁止带半初始化状态进入主循环。

## 协作约束

- 初始构建顺序固定：配置解析 -> 初始 state -> candidates -> queue -> 运行态重置 -> 视图初始化。
- 共享判定（如 pool 2x2 锚点）应复用公共解析器，禁止 Runtime/Bot 各写一套。

## 适用范围

说明进关请求如何变成可运行的 `BlastGameState`。动态难度细节见 [`Blast_DynamicDifficulty.md`](Blast_DynamicDifficulty.md)。

## 1. 初始化主链路

```text
LevelEntry
  → resolve level / profile
  → parse LevelProfileConfig
  → build difficulty context
  → build initial State / Slots / Candidates / Queue
  → reset Runtime
  → bind initial views
```

## 2. 入口职责

- `BlastLevelEntry`：进入、跳关、下一关和失败重试的统一入口。
- `BlastGameController.Loading`：向会话层转发加载请求并处理加载后的 Runtime 装配。
- `BlastGameLevelSession`：解析关卡路径、读取配置、构造初始运行态。
- `BlastLevelLoader`：把配置转换为 `BlastGameState`、初始槽位和候选。
- `BlastDifficultyContextFactory`：统一组装 Runtime、Bot、Replay 使用的难度 Context。

## 3. 数据边界

- 配置对象是输入，不在加载过程中直接作为可变运行态使用。
- `State`、`Slots`、`Candidates` 和队列由加载阶段创建；运行期由 Controller / Sim 修改。
- Runtime、Bot、Replay 可以有不同入口，但必须落到同一套初始数据和规则口径。
- 加载失败必须走安全回退，不允许带着半初始化状态进入主循环。
- 关卡分组目录统一经 `BlastLevelLoader.ResolveSeriesRelativeFolderPath`：会话注入的 `SeriesRelativeFolder` 优先，未注入时回退 `UserModuleManager.GetEffectiveLevelGroup`（Profile `LevelGroup`）；大厅难度按钮与进关加载共用此入口。

## 4. Runtime 重置

加载或回退恢复时必须重置：

- 当前关卡配置和会话状态；
- 回放状态；
- 放置流和战斗暂态；
- Presenter 的 dirty / delta 状态；
- Board、Stage、Slots 的绑定。

运行期不能用全量初始化替代增量刷新。

## 5. 代码入口

| 问题 | 入口 |
|---|---|
| 从哪里进入关卡 | `BlastLevelEntry.Start` / `TransitionLevel` |
| 如何解析关卡分组目录 | `BlastLevelLoader.ResolveSeriesRelativeFolderPath`（未注入回退 Profile） |
| 如何读取配置 | `BlastLevelConfigParser.ParseFromAsset` |
| 如何构造初始状态 | `BlastLevelLoader.BuildInitialState` |
| 如何构造初始槽位/候选 | `BlastLevelLoader.BuildInitialSlots` / `BuildCandidates` |
| 如何组装难度 | `BlastDifficultyContextFactory.BuildForEntry` |
| 加载后如何接回主循环 | `BlastGameController.Loading.LoadLevel` |
