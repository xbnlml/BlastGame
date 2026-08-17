# Player Data Logic（UserModule）


## 职责边界

- `ProfileGameUser`：服务器存档真源（定义类不可改）。
- `UserMainData`：本地运行态字段读写、时间回体、无限体力判定。
- `UserModuleManager`：首登初始化、体力/金币/等级/道具写入口与持久化调度。

## 协作边界

- 进关资格由 UserModule 输出，GameMain 只消费结果，不直接改 Profile。
- 所有消费流程遵守：资格校验 -> 内存修改 -> 持久化/同步。
- 同一字段只允许一个业务写入口，避免多处写导致口径漂移。

## 安全约束

- `Assets/Betta/.../ProfileGameUser*.cs` 属 SDK/Profile 定义层，不作为业务改动目标。
- UI 层不直接写 Profile，仅发起意图并订阅刷新结果。

## 适用范围

说明体力、金币、等级、道具和 Profile 同步的业务边界。SDK 同步接入见 [`Doc/Tools/BettaSDK_Profile_Sync_Guide.md`](../Tools/BettaSDK_Profile_Sync_Guide.md)。

## 1. 数据链路

```text
Profile / server data
  → UserMainData / UserModuleManager
  → module model
  → UI / GameMain / settlement
```

UserModule 是玩家数据业务入口；UI 和 GameMain 不直接改 Profile 文件。

## 2. 主要职责

- 体力：进关校验、扣除、无限体力和恢复时间。
  - 无限体力写入入口：`UserModuleManager.ExtendEndlessHealthAndSync`（内部 `UserMainData.ExtendEndlessHealth`，从 `max(当前截止, now)` 叠加秒数）。
  - 无限体力状态通知：`UserMainData.EndlessHealthChanged`；授予时由 Manager 触发，过期由 `SyncEndlessHealthActiveState`（挂在 `TryRecoverHealthAndSyncIfChanged`）检测后触发。
  - `UIHealthView`：无尽显示 `EndLess`/`EndLessTimeText`；非无尽显示 `HealthText`（仅数量），满体 `MaxHealthText`、未满 `HealthTimeText`。
  - `LifeNumItem`：监听 `HealthChanged` / `EndlessHealthChanged` 刷新；无尽时 `lifeTimeTxt` 显示剩余倒计时。
- 金币：余额、消费、奖励和持久化。
  - 清空：`UserModuleManager.ClearCoinAndSync`。
- 等级：玩家等级和关卡进度关联。
- 关卡记录：`ProfileGameLevelData.TimeSec` 记录本次进入关卡到结算的耗时；失败重试后覆盖为本次尝试耗时，不累计历史尝试时间。道具导致的局内重载不重新开始计时。
- 道具：库存、消耗和奖励来源。
- Profile：首登初始化、增量修改、同步和保存。
- 关卡分组：首登时 `UserModuleManager.EnsureLevelGroup` 写入并同步；**当前临时强制 `test`**（原逻辑为 50/50 随机 `funnel_b`/`test`）。缺失分组的旧存档在登录时同样补齐为 `test` 并同步。后续读取统一取 `Profile.LevelGroup`，路径解析走 `BlastLevelLoader.ResolveSeriesRelativeFolderPath`（会话注入优先，否则回退 Profile）。
- GM 面板：`Assets/Module/GM/Scripts/Logic/GMTools.Player.cs`
  - Tab `Player`：复制 UserId/DeviceId、删除账号并退出、加金币/补满体力/清空金币、无限体力 10 分钟。
  - “删除账号并退出”先读取服务端版本，再发送 `UserData.IsDelete` 请求；服务端成功后清本地 Profile 并退出应用，网络或服务端失败时不清本地数据。
  - Tab `Level`：输入关卡+分组后跳转（对齐 `BlastHudView.OnClickLoadLevel`）。
- GM 浮动入口：场景清理时，Debug/Development 包加载 `Assets/Module/GM/Prefab/GMCanvas.prefab`，由其中的 `GMBtn` 拖拽并点击打开 `UIGMPanel`（`SceneCleanupCoordinator.cs` / `GMBtn.cs`）。
- SRDebugger Options：仅保留打开 GM 面板入口（`GMTools.SRDebug.cs`）。

## 3. 边界规则

- 进关资格由 UserModule 提供，主玩法只消费结果。
- 消费必须先校验资格，再修改内存状态，最后统一保存/同步。
- 同一字段只有一个写入入口。
- UI 只展示数据和发起意图，不直接改 Profile。
- SDK 文件和 PackageCache 文件不可作为业务修改目标。

## 4. 代码定位

| 问题 | 入口 |
|---|---|
| 玩家数据总入口 | `UserModuleManager` / `UserMainData` |
| 进关体力 | `HasEnoughHealthForLevelEntry` / `TrySpendHealthAndSync` |
| 无限体力延长 | `ExtendEndlessHealthAndSync` / `UserMainData.ExtendEndlessHealth` |
| Profile 同步 | `BettaSDK_Profile_Sync_Guide.md` |
| 金币经济 | `Coin_Economy_Logic.md` |
| GameMain 失败扣体 | `BlastGameController.State.EnterLoseState` |
| SRDebugger GM Options | `Assets/Module/GM/Scripts/Logic/GMTools.SRDebug.cs`（仅打开面板入口） |
| GM 面板 Player/Level | `Assets/Module/GM/Scripts/Logic/GMTools.Player.cs` |
