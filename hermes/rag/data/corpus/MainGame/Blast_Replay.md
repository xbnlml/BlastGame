# Blast 回放逻辑（独立文档）

本文描述主游戏回放链路的当前 Unity 实现口径，覆盖数据模型、运行流程与排查锚点。

## 1. 结构分层（Data / Application / Runtime / Playback）

- Data：
  - `Runtime/BlastReplayFlowData.cs`
  - 仅承载回放状态（isReplaying、waitMs、wand 期望签名/seed、sessionPath）。
- Application：
  - `Runtime/BlastReplayFlowCoordinator.cs`
  - 负责回放推进决策（started/finished/readyToDispatch/stalled），不做 UI 或文件副作用。
- Runtime Facade / Adapter：
  - `Runtime/BlastGameReplayRuntime.cs`
  - `Runtime/BlastReplayRecordAdapter.cs`
  - `Runtime/BlastReplayRuntimeAdapter.cs`
  - 负责集中持有 player/recorder/flow data，封装录制写入、文件与会话副作用、进度上报。
  - Controller 侧局内录制走 `RecordGameplayAction` / `RecordGameplaySlotPlacement` / `RecordGameplayPowerUpUse`（固定 cycle=1 + diagnostic note 开关）；`BlastGameController.ReplayRecord` 只做启停编排与字段注入。
- Playback：
  - `Runtime/BlastGameReplayPlayback.cs`
  - 负责回放播放推进骨架（等待、快进、游标、进度、结束提示延迟）。
  - `BlastGameController.ReplayHost.cs` 仅把 Blast 局内状态与动作落地适配给公用 Playback。
- Controller Replay Adapter：
  - `Runtime/BlastGameController.ReplayDispatch.cs`
  - `Runtime/BlastGameController.ReplayPlacement.cs`
  - `Runtime/BlastGameController.ReplayPowerUps.cs`
  - `Runtime/BlastGameController.ReplayDifficulty.cs`
  - 负责 replay action 到正常 play 行为的适配：解析回放记录、校验 candidate/signature、还原 powerup/难度上下文，最终仍调用同一套落子、道具、关卡切换与运行态方法。

## 2. 回放数据

- 本地回放文件目录：`telemetry/replay/`。
- Runtime 回放文件格式：单文件 `.json`，顶层是 envelope 对象（包含 `frames` 与起始元信息）。
- `frames` 结构：`[{ frame, actions[] }]`，同一帧内动作按录制顺序保序。
- 核心类：
  - `BlastActionReplayRecorder`
  - `BlastActionReplayPlayer`
  - `BlastReplayActionRecord`
  - `BlastReplayFileEnvelope`
- 动作分类（`BlastReplayActionKind`）：
  - `Meta`
  - `Placement`
  - `PowerUp`
  - `Flow`

## 3. 数据模型字段（BlastReplayActionRecord）

| 字段 | 含义 |
|---|---|
| `type` | 回放动作类型字符串，录制与回放分发均以此为准 |
| `actionKind` | 动作大类：`Meta`、`Placement`、`PowerUp`、`Flow` |
| `level` | 录制该动作时的运行时关卡号 |
| `cycle` | 当前关卡轮次/尝试次数，主要用于回放记录 |
| `col` | 放置类动作的列坐标，回放口径为 0-based |
| `row` | 放置类动作的行坐标，回放口径为 0-based |
| `value` | 通用整型载荷，例如目标关卡号、放置数量或颜色 |
| `action_note` | 回放执行必需 token，如 `frame`、`candidate`、`dd*`、hammer 锚点 |
| `note` | 可选附加文本，用于校验与诊断；默认录制链路为空 |
| `waitStartFrame` | Bot 诊断用等待区间起始帧，回放分发忽略 |
| `waitEndFrame` | Bot 诊断用等待区间结束帧，回放分发忽略 |
| `waitDurationMs` | Bot 诊断用等待时长，单位毫秒，回放分发忽略 |
| `waitWindowCount` | Bot 诊断用等待窗口数量，回放分发忽略 |
| `waitNote` | Bot 诊断用等待说明，回放分发忽略 |

### 文件与帧容器字段

| 对象 | 字段 | 含义 |
|---|---|---|
| `BlastReplayFileEnvelope` | `version` | 回放文件格式版本，当前默认 `3` |
| `BlastReplayFileEnvelope` | `sessionId` | 回放会话标识 |
| `BlastReplayFileEnvelope` | `startLevel` | 会话起始关卡 |
| `BlastReplayFileEnvelope` | `cycle` | 会话轮次/尝试次数 |
| `BlastReplayFileEnvelope` | `seed` | 本次回放使用的随机种子 |
| `BlastReplayFileEnvelope` | `frames` | 按逻辑帧分组的动作列表 |
| `BlastReplayFrameRecord` | `frame` | 逻辑帧编号 |
| `BlastReplayFrameRecord` | `actions` | 当前帧内按录制顺序排列的动作 |

### 回放会话索引字段（BlastReplaySessionInfo）

`actionCount`、`fileName`、`filePath`、`level`、`cycle`、`relativePath`、`seed`、`sessionId`。

其中 `fileName` / `filePath` / `relativePath` 用于文件定位，`actionCount` 用于动作数量统计，其他字段用于会话索引与展示。
- 语义要点：
  - 逻辑帧真值只在 `frames.frame`；action 本体不再冗余 `logicFrame` 字段。
  - 录制时会在 `action_note` 中附带 `frame=...` 执行锚点（回放等待/派发以此为准）。
  - `action_note` 仅承载“回放执行必需 token”（如 `candidate`、`dd*`、hammer 锚点）。
  - `note` 在默认录制链路下为空；回放执行仅依赖 `action_note`。
  - `load_level.action_note` 携带动态难度快照与关卡分组（Runtime 与 Bot 对齐）：
    - `levelGroup`（录制时 `BlastLevelLoader.SeriesRelativeFolder`，如 `funnel_b` / `test`；回放启动与每条 `load_level` 派发前写入 loader，结束后恢复 Profile 分组）
    - `btNonAttackTransitionFoldPolicy`（`FlyingIn / Merging / Closing` 的折叠策略，Bot 导出回放时记录，Runtime 回放开始时一次性恢复）
    - `ddTier`
  - `ddLevel`
  - `ddCurrentCycle`
    - `ddStartDifficulty`
  - `ddDifficultyLoopOffset`
  - `ddLevelDifficultyLevel`
    - `ddShuffleSplitCount`
    - `ddShuffleSplitRatios`
    - `ddShuffleOverflowFactor`
  - `ddLevelDifficultyFactor` 不参与回放判定；洗牌乘数统一读取全局 `BlastDataConfig`。
  - **`load_level.action_note` 动态难度字段完整性**：Bot 导出 replay 时 `BuildReplayLoadLevelNote` 必须写入全部有效 `dd*` 字段（`ddTier`、`ddLevel`、`ddCurrentCycle`、`ddStartDifficulty`、`ddDifficultyLoopOffset`、`ddLevelDifficultyLevel`、`ddShuffleSplitCount`、`ddShuffleSplitRatios`、`ddShuffleOverflowFactor`），并写入 `btNonAttackTransitionFoldPolicy`；任一缺失或非法 → 直接判定 `replay_invalid_load_level_note` 并中止回放，**不再回退 `level - 1` / `startDifficulty × cycle` 等历史口径**。

## 4. 会话与文件路径

- 回放目录解析：`BlastReplayPaths.GetReplayDirectory()`
  - Editor 下使用项目根目录 `telemetry/replay`
  - 非 Editor 下使用 `persistentDataPath/telemetry/replay`
- 会话文件：`<sessionId>.json`
- Runtime 会话 id：`player-{yyyy-M-d_HH-mm-ss}-L{level}`（示例：`player-2026-4-29_19-18-00-L55`）
- Bot 会话 id：`bot-{yyyy-M-d_HH-mm-ss}-L{level}`（示例：`bot-2026-4-29_19-18-00-L1`）
- 同秒重复导出防冲突：若同名已存在，自动追加 `-001/-002/...` 后缀。

## 5. 录制时机

- 录制“显式动作 + 对应逻辑帧号”，不录制每次攻击命中目标格。
- 攻击目标由回放时同一 `BlastAttackSystem` 状态确定：普通目标依赖跨 `UpdateAttacks()` 的按颜色待攻击队列与 per-slot row sweep cursor，在开火瞬间懒选择；特殊块实时扫描并可插队。
- `BlastAttackSystem` 实例在 Controller 生命周期内复用（槽位数不变时不重建）；**每次 `LoadLevel` 成功后会调用 `ResetAllCombatTargetingState()`**，清空普通攻击队列、已消费坐标、特殊目标锁定、per-slot row sweep 与底行缓存，对齐 Bot 每局 `new BlastAttackSystem()` 的干净开局。**运行中落子/战斗 tick 不再额外清空 targeting 数据**，避免与录制时的攻击顺序分叉。
- 回放文件不保存攻击命中目标、不保存普通队列、不保存 cursor，也不保存 special focus；Runtime 实玩、Runtime 回放与 Bot 导出的 placement replay 都通过同一攻击系统状态重算目标。
- 录制会话起点（`session_start`）在关卡重置后启动，确保新会话的帧基准与 `load_level/place_slot` 一致（从同一局内逻辑帧计数起点开始）。
- 录制落盘流程：先构造 `BlastReplayFileEnvelope` 对象，再做 `JsonUtility.ToJson(envelope)` 写入。
- 动作包含关卡加载、候选点击、道具使用、结果状态等。
- `test user`（`UserModuleManager.isTestUser=true`）进入关卡时不会启动录制会话；用于回放纯展示场景时不生成新的 player 录制文件。
- 典型动作类型（`BlastGameActionTypes`）：
  - 会话/关卡：`session_start`、`load_level`、`session_end`
  - 放置：`place_slot`、`place_slot_magnet`
  - 道具：统一采用 `<powerup>_(buy|use)_(click|confirm|cancel)` + `<powerup>_effect` 命名；回放文件仅保留“使用链路”动作，`*_buy_*` 购买动作仅用于 BI 打点，不写入回放文件
  - 流程：`reload_level`、`next_level`、`jump_level`、`lose_retry_health`
  - 调试：`debug_reload`、`debug_next`、`debug_keylock_tick`
  - Magnet 新协议链路：`magnet_buy_click -> magnet_buy_confirm|magnet_buy_cancel -> magnet_use_click -> place_slot_magnet`
    - `magnet_buy_cancel` 仅表示用户取消本次道具确认，不应触发 `magnet_use_click/place_slot_magnet`。

## 6. 回放入口与推进

- 启动入口：`BeginReplayFromFile(...)`（内部会先 `LoadLevel()`，从而重置 `BlastAttackSystem` targeting 状态）
- 中止入口：`AbortReplay()`
- 推进入口：`StepReplay(bool allowGameplayActions)`，由 `FixedUpdate` 分战斗前/战斗后两个相位调用。
- 手动回放入口：`ReplayFromReplayJson(...)`（来自 `GameReplayDataManager` 的 Odin 按钮“回放”；支持直接 JSON 或 `.json` 文件路径。JSON 输入会解析为 envelope 后以内存方式启动回放，不再落盘 `manual_replay_*.json`；文件路径输入仍复用 `BeginReplayFromFile(...) + FixedUpdate` 回放推进，保持与运行时同一消费链路）
- `GameReplayDataManager.replayJson` 支持两种输入：直接粘贴回放 JSON，或填写本地 `.json` 文件路径（可通过 Odin 按钮“选择回放文件”填充）。
- 推进规则：
  - 逻辑推进由 `FixedUpdate` 驱动，`Update` 只负责输入与渲染刷新。
  - 每帧由 `BlastReplayFlowCoordinator.EvaluateTick(...)` 决定是否推进。
  - `SetWaitByNextAction(...)` 从下一条动作 `action_note` 解析 `frame=`，并将其作为 `replayWaitUntilLogicFrame`。
  - 帧口径：所有动作统一按 `frame` 原值派发；录制帧统一由 `FixedUpdate` 的 `LogicFrame` 写入，不再使用 `Update` 的 `frame+1` 映射。
  - 回放文件要求 `frames` 按 `frame` 非递减顺序；出现倒序（`current < prev`）时拒绝启动回放。
  - 回放加载关卡时，动态难度输入快照（`ddTier/ddStartDifficulty/ddGameLevel|ddLevel/ddCurrentCycle/ddDifficultyLoopOffset/ddDifficultyLevel|ddLevelDifficultyLevel/ddShuffleSplitCount/ddShuffleSplitRatios/ddShuffleOverflowFactor`）从 `load_level.action_note` 严格还原；新录制双写 `ddGameLevel` 与 `ddDifficultyLevel`，读取时新 token 优先、旧 token 回退。
- 回放 `load_level` token 走严格校验：`levelGroup`、`dd*`、`qbPreferBfs`、`qbEnableParity`、`btNonAttackTransitionFoldPolicy` 缺失或非法时直接判定 `replay_invalid_load_level_note` 并中止，不再回退读取玩家当前配置。
  - 回放加载关卡时，若 `load_level.action_note` 含 `levelGroup`，进关前使用该分组解析关卡资源；缺失时使用当前 Profile 分组。
  - 当存在下一条动作且无瞬态阻塞（子弹飞行、钥匙解锁、关卡切换、道具阻塞）时即可派发；回放在 combat 前先消费当帧 replay action（含 placement / powerup / flow），再推进战斗 tick；不再硬依赖 `runState == Playing`。
  - 回放瞬态阻塞改为“按动作类型判定”：`place_slot/place_slot_magnet` 先等到“真可落子”再派发，且落子阶段复用主路径但绕开实玩输入门控（`IsStagePlacementInputBlockedForAction + IsHammerSelecting + _isHammerStageInputBlocked`）；非 placement 动作仍使用 FixedUpdate 逻辑态阻塞（`_bullets.Count/_pendingKeyUnlocks.Count` + placement flow 未到 `ClickReady`）。
  - 回放在每个 `FixedUpdate` 派发 replay action 前，会先消费本帧已到时的 stage placement input unlock；这样 `frame=N` 的落子可与实玩 `Update` 点击共享同一帧入口，不会因为“先检查回放、后解锁输入”而晚 1 tick。
  - 当动作队列已耗尽时，仅在“仍有瞬态阻塞”场景继续等待；阻塞清空后直接标记 `replay_finished`（不再以 `runState` 作为结束前置条件）。
  - `place_slot/place_slot_magnet` 在回放态允许 `runState=Ended` 时继续补消费队列尾部动作，避免“已通关但末尾动作未执行”。
  - 当下一条是道具动作（含 `magnet_buy_* / magnet_use_* / place_slot_magnet / wand_use_* / wand_effect / hammer_use_* / hammer_effect / rollback_use_* / rollback_effect`）时，回放会绕过 powerup 阻塞并按记录动作直接派发。
  - `place_slot/place_slot_magnet` 回放分发按“真实落子成功”判定，且严格依赖 `action_note` 中的 `candidate=cellIndex` 做候选一致性校验；缺失/解析失败/命中失败都会直接判定该动作失败。
  - `place_slot` 与 `place_slot_magnet` 回放执行复用 `TryApplyStageCellClick(..., bypassInputGate:true)`；回放层仍只负责 candidate 校验与动作分发，不再改写一套独立落子逻辑。
  - 回放落子视觉链路与主流程一致：同样注册并收口 placement flow token（`Begin/Mark/CompleteStageSlotPlacementFlow`），避免动画窗口与 combat 门控出现分叉时序。
  - `BlastAttackSystem` 按槽位对象引用自动同步 targeting 状态（`SyncTargetingStateBySlotRefs`）；runtime/replay 共用同一规则。
  - 槽位对象引用变化时重置该槽位 targeting 并归零 cooldown。
  - 回放执行落子时不再上报 `level_play/place_slot` BI（`TrackLevelPlayPlaceSlot` 在 replay 直接返回），避免回放污染实玩埋点。
  - 实玩与回放统一战斗门控口径：`FixedUpdate` 的 combat 推进不依赖 placement flow UI 状态；实玩由 `PropUseUi.IsOpen`（道具使用弹板）阻塞，回放无真实弹板时以磁铁/锤子选择态对齐。
  - `place_slot/place_slot_magnet` 回放落子成功后保持与实玩一致的流程衔接；`place_slot_magnet` 在逻辑层同步退出 Magnet 选择态（`IsMagnetSelecting=false`），避免道具态持续阻塞战斗推进。
  - 回放执行失败由动作级失败触发（非法 action / candidate 不可用 / 关键 token 缺失）。
  - 回放推进改为单入口 `Step()`；内部保留 pre-combat/gameplay 两阶段，但 `Waiting` 诊断在单次 `FixedUpdate` 只输出一次，避免重复日志噪音。
  - `SlotAttackFly` 的 `Build context failed` 在回放态按 UI 特效链路告警处理（`[Blast][SlotAttackFly]` warn），不作为数据一致性失败判据；该分支仅表示飞行动效上下文构建失败（特效丢失），不改变逻辑推进。
  - `SlotAttackFly` 命中格坐标若落在当前不可视棋盘行（`targetY` 超出 viewport），`BlastBoardView.TryGetCellWorldPos` 按当前棋盘布局公式反解虚拟格 world pos，不依赖可视 cell 实例。
  - `place_slot/place_slot_magnet` 回放不再走独立的候选直塞重试逻辑；执行失败会直接判定 `replay_stalled`。
  - 若落子因状态漂移导致无法放置，会进入 `replay_stalled`，不再继续吞后续动作。
  - 道具回放动作会弹统一“动作提示窗”（仅 4 个标准道具：`magnet_use_click/wand_use_click/hammer_use_click/rollback_use_click`）；`*_use_confirm`、`magnet_buy_confirm/magnet_buy_cancel` 与 `fail_revive_use_confirm` 不弹窗直接推进。
  - 提示窗仅用于展示，不再作为固定毫秒门控；回放推进节奏统一由“下一条动作的 `frame`”驱动，到达目标帧后自动继续，无需用户确认交互。
  - `wand/rollback/fail_revive` 在录制时会先写入 `*_use_confirm`，再写入 `*_effect`；其中 wand/rollback 回放提示窗在 `*_use_click` 弹出，并按后续动作 `frame` 自动推进到确认/效果动作。
  - 回放态会跳过 fail-revive 业务确认窗（`RequestFailReviveTempSlots` → `UIGameContinueView`）；是否使用仅由 `fail_revive_effect` 回放动作决定。
  - 锤子动作 `hammer_use_confirm/hammer_effect` 以 `value=颜色` 为单一真值；回放分发不再依赖记录时点击格 `x/y`。
  - `hammer_apply/hammer_use_confirm` 相关锚点（`cellIndex`、`removed`）从 `action_note` 读取；锚点不可用时回退到“首个同色可选块”。
  - 下一条动作等待按 `logicFrame` 推进：当前逻辑帧达到下一动作帧号后再派发。
  - 回放等待跳过（FastForward）：当“下一条动作等待帧差”大于 `100` 且当前无关卡加载阻塞/瞬态阻塞/道具阻塞时，Playback 会自动快进大段空帧，仅保留尾部约 `20` 帧缓冲，再继续正常推进；同时会同步 `logicFrame/accumulatedMs`，并按跳过的固定时长扣减 `dropLandRemainMs`（到期同步重置 `dropSequenceIndex`），再输出 `[BlastReplay][FastForward]` warn 日志，避免长空窗导致回放等待过久。
  - 回放执行期间使用 `isApplyingAction` guard，避免“回放动作再次被录制”。
  - 回放结束时仍先按原口径上报 `replay_finished`；成功/失败结果提示窗仅延后约 `20` 个逻辑帧显示，避免最后一帧表现尚未稳定时过早遮挡画面。
  - 回放消费读取 `action_note`；缺少关键动作字段的记录不可回放。

## 7. 进度与状态

- 常见状态：
  - `replay_started`
  - `replay_finished`
  - `replay_stalled`
  - `replay_mismatch_wand`
- 回放在 `replay_started/replay_finished/replay_stalled` 关键节点会输出
  `[BlastReplay][Cursor] status=...;cursor=...;total=...;remaining=...;remainingClearTargets=...`。
  - 其中 `remaining` 表示“动作队列剩余数”，不是盘面块数量；
  - 盘面清目标剩余请看 `remainingClearTargets`。
- 当回放 `result=win`、`remainingClearTargets>0` 且 Stage/Slot 未同时清空时，会额外上报 `replay_mismatch_result` 并打印 `[BlastReplay][Mismatch]`，用于快速识别“动作不足/状态漂移”；不再以队列耗尽豁免该校验。
- `place_slot` 若记录了 `candidate=cellIndex` 且当前列 front 候选不一致，会上报 `replay_mismatch_candidate` 并打印
  `[BlastReplay][CandidateMismatch]`（含动作序号、expected/runtimeCandidate、列行）；runtimeCandidate 统一复用实玩入口同一候选选择器（`PlaceSlot`=front，`PlaceSlotMagnet`=magnet），避免 replay 侧独立分叉判定。
- `wand_use` 附带 seed 与签名，回放时用于一致性校验。

## 8. 当前协议约束

- 文件使用 frame/action envelope；同一帧内动作保持录制顺序。
- 播放由 `FixedUpdate` 和 action frame 驱动。
- Runtime、Bot、Replay 共用动作模型和正常玩法入口。
- `load_level` 必须携带回放所需的难度与运行上下文；缺失关键 token 时回放失败。
- 回放期间使用 guard，避免回放动作再次写入录制文件。
- 回放结果和进度只反映回放会话，不污染实玩 BI。

## 9. 排查建议

- 先确认 session 文件是否持续写入。
- 再检查动作序列是否覆盖当前测试路径。
- 若出现回放偏差，优先检查：
  - 随机种子是否记录并复用；
  - 候选签名是否一致；
  - 关键状态切换（运行态、道具态）是否同步。
- 若 `slots` 有弹药但长时间不下降，或 `queue=` 与录制不一致而 `cands` 仍相同：
  - 先确认本次回放是否经 `BeginReplayFromFile` → `LoadLevel` 进入（应已执行 `ResetAllCombatTargetingState`）；
  - 再对比首个分叉动作对应的 `frame/candidate` 与回放日志中的 `StepTrace`，区分“攻击未推进”与“落子/合并/队列消费顺序”问题；
  - **不要在运行中手动清空 `BlastAttackSystem` 队列或 row sweep**（与 Bot 录制口径不一致，会导致后续 `queue` 前缀颜色漂移）。

## 10. 类功能定位

| 类/文件 | 功能 | 路径 |
|---|---|---|
| `BlastReplayFlowData` | 回放运行时状态容器（Data 层） | `Assets/GameModule/GameMain/Script/Runtime/BlastReplayFlowData.cs` |
| `BlastReplayFlowCoordinator` | 回放推进决策（Application 层） | `Assets/GameModule/GameMain/Script/Runtime/BlastReplayFlowCoordinator.cs` |
| `BlastReplayRuntimeAdapter` | 回放文件读取、会话副作用桥接（Runtime Adapter） | `Assets/GameModule/GameMain/Script/Runtime/BlastReplayRuntimeAdapter.cs` |
| `BlastReplayRecordAdapter` | 回放动作录制与写入桥接（Runtime Adapter） | `Assets/GameModule/GameMain/Script/Runtime/BlastReplayRecordAdapter.cs` |
| `BlastGameReplayRuntime` | 公用回放 Runtime 门面，集中持有 flow data / player / recorder 并封装录制、读档、进度上报 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameReplayRuntime.cs` |
| `BlastGameReplayPlayback` | 公用回放 Playback 引擎，负责 `Step`、等待/快进、游标推进、进度与结束提示调度 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameReplayPlayback.cs` |
| `BlastGameController.ReplayHost` | Controller 局内动作适配层，把状态、道具、落子、UI 提示桥接给公用 Playback | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.ReplayHost.cs` |
| `BlastGameController.ReplayDispatch` | 回放 action 分发适配层，按 action type 调用同一套 play 落地入口 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.ReplayDispatch.cs` |
| `BlastGameController.ReplayPlacement` | 回放落子适配层，解析 candidate 并调用正常 candidate 入槽与刷新逻辑 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.ReplayPlacement.cs` |
| `BlastGameController.ReplayPowerUps` | 回放道具适配层，按 replay 记录还原 hammer/wand/rollback/fail-revive 行为并调用正常道具入口 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.ReplayPowerUps.cs` |
| `BlastGameController.ReplayDifficulty` | 回放难度适配层，从 `load_level.action_note` 还原动态难度与队列参数上下文 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.ReplayDifficulty.cs` |
| `BlastActionReplayRecorder` | 回放动作录制器 | `Assets/GameModule/GameMain/Script/Runtime/BlastActionReplayRecorder.cs` |
| `BlastActionReplayPlayer` | 回放动作播放器 | `Assets/GameModule/GameMain/Script/Runtime/BlastActionReplayPlayer.cs` |
| `BlastGameController.Gameplay` | 正常 play loop 与战斗 tick 入口；只保留 replay playback 推进钩子，不承载 replay action 解析/落地细节 | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.Gameplay.cs` |
| `BlastGameController.PowerUps` | 正常 play 道具入口与状态维护；replay-only 道具适配已拆到 `BlastGameController.ReplayPowerUps` | `Assets/GameModule/GameMain/Script/Runtime/BlastGameController.PowerUps.cs` |

维护规则：回放新增动作类型或改派发路径时，必须同步更新本表。
