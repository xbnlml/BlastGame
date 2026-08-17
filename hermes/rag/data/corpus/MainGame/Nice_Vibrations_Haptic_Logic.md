# Nice Vibrations 触感（Preset + Tone）

业务触感唯一入口：`GameHaptic` + `GameHapticManager`（单例）。已移除 SDK `HapticModule` / `IHapticSystem` 业务依赖。

## 范围

| 做 | 不做 |
|---|---|
| Preset（9 种） | Advanced Clip |
| Tone（amp + freq + duration） | Curve Mode |
| Catalog SO + `Play(id)` | 自定义 HapticClip Mode |
| 冷却 / 连震 / 顺序震动 | 24 场景默认表 |
| GM「震动NV」试播 + 复制 JSON | 批量铺更多玩法调用点 |

## 入口

| 职责 | 类 | 路径 |
|---|---|---|
| 管理器（开关同步、Catalog） | `GameHapticManager`（`Singleton`） | `Assets/GameModule/Common/Script/Haptic/GameHapticManager.cs` |
| 播放 API | `GameHaptic` | `Assets/GameModule/Common/Script/Haptic/GameHaptic.cs` |
| Catalog SO | `GameHapticCatalog` | `Assets/GameModule/Common/Script/Haptic/GameHapticCatalog.cs` |
| 默认 asset | — | `Assets/GameModule/Common/ConfigSo/GameHapticCatalog.asset` |
| GM 真机试震 | `UIHapticNvTest` | GM 模块 UI（震动 NV 试震） |

`GameMain.InitProfile` 在 `UserModuleManager.InitializeFromProfile` 后调用 `GameHapticManager.Instance.Init()`；**不**走 `IApplicationModule`。

## 通用按钮触感

- `UIButton` 在 `mIsCanPlayVibrate` 时发 `EventCommonBtnHaptic`，不引用游戏模块。
- `GameHapticManager` 订阅后 `GameHaptic.Play("1")`（Catalog `CommonBtnPreset`）。
- 覆盖：点击放置（StageCell）、道具、设置、通用按钮、使用道具等主动点击。

## 玩法触感映射（Catalog id）

| 场景 | 调用点 | Catalog 名称 | Catalog id |
|---|---|---|---|
| 通用按钮点击 | `UIButton` → `EventCommonBtnHaptic` | CommonBtnPreset | `1` |
| 小动物 res | `BlastSlotCellView.PlaySlotEatFeedbackRes3` | CommonGameRes1 | `3` |
| 小动物 merge | `BlastSlotCellView.EnterMergingVisualState` | CommonGameRes1 | `3` |
| 临时金币收集（Objective res） | `BlastBoardCellView.PlayObjectiveHitVisual` | CommonGameRes1 | `3` |
| 小费罐炸掉（Objective close） | `BlastBoardCellView.PlayCloseVisual` | CommonGameRes2 | `4` |
| 飞币收集到位（关卡内进度条） | `BlastLevelProgressView.PlayArriveRes` | CollectRes | `10` |
| 飞币收集到位（关卡外/结算顶栏） | `CurrencyNumItem.PlayCollectArriveFeedback` | CollectRes | `10` |
| 胜利弹板 1 星 | `UIGameWinView.TryPlayCustomShowAnimation` | LevelWin1（sequence） | `1001` |
| 胜利弹板 2 星 | 同上 | LevelWin2（sequence） | `1002` |
| 胜利弹板 3 星 | 同上 | LevelWin3（sequence） | `1003` |
| 失败弹板 | `UIGameLoseView.TryPlayCustomShowAnimation` | LevelFail | `8` |
| 复活弹板 appear | `UIGameContinueView.TryPlayCustomShowAnimation` 入场 | LevelRevive | `9` |
| 复活弹板 1to2 | 有 FailOffer 时 `appear1→1to2` 再补播 | LevelRevive | `9` |

常量：`CatalogIdCommonBtn` / `CatalogIdCommonGameRes1` / `CatalogIdCommonGameRes2` / `CatalogIdCollectRes` / `CatalogIdLevelWin1..3` / `CatalogIdLevelFail` / `CatalogIdLevelRevive`。

说明：Catalog 仍保留 id=`2`（`CommonTone`），当前无业务调用。胜利序列 `1001..1003` 步骤引用 Winstar1/2/3（id=`5`/`6`/`7`），序列内自带 delay。复活触感：任意 `appear1` 入场播一次；有 FailOffer 进入 `1to2` 时再补播一次。飞币到位 `CollectRes`：关卡内进度条 CoinNum `res`、关卡外/胜利页顶栏 `CoinNumObj_res` 共用；连续到位时 `AnimatorManager.PlayAnimator` 用 `CrossFade(0)` 强制从第 0 帧重开。

## Tone 规则

```text
duration <= 0.12s  →  HapticPatterns.PlayEmphasis(amp, freq)
duration >  0.12s  →  HapticPatterns.PlayConstant(amp, freq, duration)
```

常量：`GameHaptic.ToneEmphasisMaxDuration`。

## 冷却 / 连震

与旧语义一致（按 Catalog `id` / 直调 key）：

- `pulseCount == 1`：`intervalMs` = 同 key 冷却
- `pulseCount > 1`：`intervalMs` = 脉冲间距（不做 Play 冷却）；协程宿主 `UtilsCoroutine`

## 开关

- 存档键：`SettingData["HapticSwitch"]`（1=开，0=关）
- `GameHapticManager.SetHapticsEnabled(bool)` 写存档并同步 `HapticController.hapticsEnabled`；关时 `StopAll`
- `IsHapticsEnabled` / `SyncHapticsEnabled`；播放前会再同步
- 设置页：`UISettingsView` / `BlastMainSettingView` 点击切换走 `SetHapticsEnabled(!IsHapticsEnabled())`

## API

```csharp
GameHaptic.Play("demo_tone");
GameHaptic.PlayPreset(HapticPatterns.PresetType.LightImpact);
GameHaptic.PlayTone(0.7f, 0.5f, 0.08f);
GameHaptic.Stop("demo_tone");
GameHaptic.StopAll();
```

玩法示例：小费罐 Objective close → `GameHaptic.Play(CatalogIdCommonGameRes2)`。

## GM「震动NV」→ 编辑器回写

1. GM →「震动NV」→ **打开震动NV试震**  
2. 顶部选 **Preset / Tone**（参数区按类型刷新）  
   - Preset：Preset 枚举 + 次数 + 间隔 + 配置Id  
   - Tone：振幅 / 频率 / 时长 + 次数 + 间隔 + 配置Id  
3. **试震** / **停止** / **复制配置**  
4. 编辑器选中 Catalog → **从剪贴板导入 Entry**

GM 的「震动序列」标签只用于临时试播，不读取或写入 `sequences`：在 `Steps` 输入 `延迟,配置Id,...`（如 `3,1,2,2,2,3`），点击 **试播Steps**。每对数字对应一步；延迟单位为秒，配置 Id 引用已有单次 Entry；成功解析后输出步骤汇总日志。单次震动参数仍保留在「震动NV」标签。

参数输入框为宽版布局；切换参数区刷新时，同一参数会保留已输入的值。

复制 JSON 按 mode 互斥：Preset 只带 `preset`；Tone 只带 `amplitude`/`frequency`/`duration`；共用 `pulseCount`/`intervalMs`/`id`。

## Catalog Entry

Preset 与 Tone **互斥**（Inspector 用 Odin `ShowIf` 切换）：

- `mode`：`Preset | Tone`
- Preset 时只填：`preset`
- Tone 时只填：`amplitude` / `frequency` / `duration`
- 两种都填：`pulseCount` / `intervalMs`

默认示例：`demo_preset`、`demo_tone`。

## 顺序震动配置

同一 `GameHapticCatalog` ScriptableObject 的 `sequences` 可新增序列配置；`GameHaptic.Play(sequenceId)` 自动播放。每个步骤按列表顺序处理：先等待 `delayTime`（秒），再按 `hapticId` 引用并播放已有 Entry。再次播放同一个序列 ID 或调用 `GameHaptic.Stop(sequenceId)` 会取消该序列的剩余步骤。

关卡胜利 LevelWin1/2/3（id=`1001`/`1002`/`1003`）即为此类序列。

## 依赖

- `HotUpdate.asmdef` 引用 `Lofelt.NiceVibrations`（GUID `57a0b9bc628ab4740af4b6f1f0b2e134`）
- 包路径：`Assets/Plugins/ThirdSdk/NiceVibrations`
