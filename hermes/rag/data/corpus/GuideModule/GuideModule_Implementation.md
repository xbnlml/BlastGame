# GuideModule 引导系统实现文档（压缩版）

> 状态：运行时链路可用（配置读取、首次进入触发、进度续播与推进控制已接通），其余高级能力待联调
> 更新：2026-08-03

---

## 1. 本轮关键改动（已落地）

1. **RootView 窗体化**
   - `GuideScenarioRootView` 改为 `BlastUIWindowView<GuideScenarioRootViewBinder>`。
   - Prefab 根节点挂 `UIWindowConfig` + `GuideScenarioRootViewBinder`（不再挂 RootView MonoBehaviour）。
   - `GuideScenarioManager` 通过 `UIManager.Open/Close` 开窗；段落内常驻复用，结束 `Close(true)`。

2. **连续引导切换**
   - 步骤复用 RootView 和已加载资源；仅当实际背景从无到有、从有到无或前后 `BG` 配置不同才对背景层做 `0.2s` 渐隐渐现，并在总时长中点切换内容（alpha `1 → 0.5 → 1`），避免完全透明漏出底层游戏画面；同时给该次自动步骤的 `Auto_Time` 补 `0.2s`。
   - 角色、对话框等步骤内容在背景过渡的刷新点直接切换；背景不变时整步直接刷新。`SegmentID` 仅用于分组、排序和完成进度记录。
   - Binder `AnimationMode = None`，避免窗体入场动画拖住首帧。

3. **DialoguePanel 布局**
   - 左右角色与对话框统一在 `DialoguePanel` 下；`Dialog_Offset` 作用在 DialoguePanel，连带移动角色。
   - `Adaptation = 0` 显示 `DialoguePanel`；`Adaptation = 1` 隐藏对话框，读取 `Character` 预设实例化到 RootView Binder 的 `prefabPanel`，并用 `Dialog_Offset` 设置其 `anchoredPosition`。同名预设跨步骤复用，不同名释放后重载。
   - `Avatar_Position`：`Left/Right` 显示对应角色与 SpeakerBg，并写入 `Character`；`None`（含遗留 Center）两侧关闭。
   - 已移除 NextHint 点击提示；全屏点击推进保留。
   - `GuideScenarioManager.Instance.NoticeNextGuide()` 是通用业务事件推进入口。业务成功后直接调用，例如改名成功后通知引导进入下一步；是否触发以及触发时机由业务自行控制，不依赖 `Next_Action` 配置。

4. **既有能力（摘要）**
   - 配置模型扩展：`GetDialogOffset` / `GetAvatarPosition` / `GetNextAction` / `ShouldStopAfterCurrentStep`。
   - `Next_ActionStop` 结束当前播放段；进度落盘 `ProfileGameGuideModule.GameGuideState` 保存最后完成的 Sequence。
5. **首次进入触发与续播**
   - 触发定义位于 `GuideScenarioTriggerConfig`，`SegmentID` 仍只负责步骤分组，关卡条件独立配置。
   - 关卡加载前记录 `GameLevelDatas` 是否已有任意记录及当前关记录，避免 `MarkLevelPlayingState(1)` 造成首次进入误判。
   - 进入引导时先恢复任意未完成 Segment，再判断当前关卡的新触发；`NEWGUY` 完成后可继续触发同一次首关进入的 `LEVEL1`。
   - 引导开始写入 `0`，每推进一步写入已完成 Sequence，达到最大 Sequence 才视为完整完成。
6. **引导总开关**
   - `GuideScenarioManager.enableGuidePopup` 在 Inspector 中控制整套引导弹窗逻辑，默认开启。
   - 关闭时会停止当前引导，并阻止自动触发、业务手动播放和编辑器测试播放。

---

## 2. 当前核心文件（精简）

### 2.1 Core
- `Assets/GameModule/GuideModule/Script/Core/GuideScenarioEnums.cs`
  - 引导枚举 + `GuideOffsetParser`
- `Assets/GameModule/GuideModule/Script/Core/Guide_Scenario.cs`
  - `GuideScenario` 扩展方法（转换/解析/停止判定）
- `Assets/GameModule/GuideModule/Script/Core/GuideScenarioConfigRepository.cs`
  - 读：`ConfigManager.GetGuide_ScenarioList()`
  - 写：保留 JSON 写回能力（供编辑器保存）
- `Assets/GameModule/GuideModule/Script/Core/GuideScenarioConfigValidator.cs`
  - 基础校验（SegmentID/Sequence/重复 key/Auto_Time）；仅校验当前播放段，挖洞点击不再依赖 `Target_Position`
- `Assets/GameModule/GuideModule/Script/Core/GuideScenarioTriggerConfig.cs`
  - 首次进入触发类型、关卡映射与 `LEVEL1` 前置 Segment 配置

### 2.2 Runtime
- `Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioManager.cs`
  - 段播放、首次进入触发、未完成段恢复、`UIManager` 开窗常驻、步骤瞬间 Refresh、`AdvanceOrStop`、进度落盘
- `Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioAdvanceResolver.cs`
- 推进方式判定（`Auto_Time` 控制自动推进）
- `Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioSession.cs`
  - 当前段会话状态
- `Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioTargetResolver.cs`
- 挖洞区域命中判定

### 2.3 UI / Editor
- UI：`GuideScenarioRootView`（BlastUIWindowView）+ `GuideScenarioRootViewBinder` / `DialogueView` / `CharacterView` / `HandView` / `MaskHoleView`
- Prefab：`Assets/GameModule/GuideModule/Prefabs/View/GuideScenarioRootView.prefab`
- 挖洞：`GuideScenarioMaskHoleView` → `UiInverseTextureMask`；按 `BG_Mask_Type` 切换 `SquareHole`（2）/`CircleHole`（1），从 `BG_Mask_Size` 的 `x/y` 设置位置、`z/w` 设置尺寸。引导通过 `SetHoleClickDetection(true, callback)` 为所有挖洞步骤开启洞区点击检测；`Allow_Tap=0` 时洞内按下推进，`Allow_Tap=1` 时等待洞内抬起，让底层 UI 先完成点击后再推进。
- 背景：普通 `BG` 从 `GuideScenarioBackgroundAtlas` 读取到 `backgroundImage`；`BG=mask` 显示配置好的 `maskImage`；有 `BG_Mask_Type` 时两者都隐藏，只显示挖洞遮罩。
- 挖洞步骤强制目标点击，不响应自动推进和全屏点击。
- 手势：`Hand_Type=0` 隐藏，`1` 显示 `Arrow`，`2` 显示 `Hand`；根节点位置跟随挖洞位置，子节点使用 `Hand_Offset` 的 `anchoredPosition` 与 `Hand_Rotation` 的 Z 轴旋转。
- 触感：步骤表现刷新完成时，若 `Vibrate_Time > 0`，通过 `GameHaptic.Play` 播放对应 Catalog ID；`-1` 表示不播放。
- 震屏：步骤表现刷新完成时，若 `Shake_Time > 0`，将该毫秒值传给 `MMPositionShakerManager` 驱动 RootView 震屏；管理类内部转换为秒，固定 `ShakeSpeed=30`、`ShakeRange=30`、方向 `(1,1,0)`；RootView 无需预挂 Shaker，Manager 会按 `RectTransform` 自动获取或添加。
- Editor：`GuideScenarioEditorWindow/State/Serializer/PreviewController`

---

## 3. 配置字段（仅保留高频）

- 段与顺序：`SegmentID`、`Sequence`
- 展示：`Avatar`、`Avatar_Position`、`Character`、`Content`、`BG`
  - `Avatar_Position`：`0=None / 1=Left / 2=Right`（不再使用 Center）；驱动左右角色与 SpeakerBg/SpeakerText
  - 角色统一读取 `Avatar` 图集图片；`Actor_Preset`、`Actor_State` 暂不参与运行时表现
- 交互：`Next_Action`（0全屏/1目标）、`Hand_Offset`；目标点击通过挖洞区域命中判断
- 挖洞点击穿透：`Allow_Tap=0` 时洞内点击仅推进引导并拦截游戏内容；`Allow_Tap=1` 时洞内点击推进引导并穿透到底层游戏按钮。
- 文本：`Text_Appear`、`Text_Speed`
- 打字机：`GuideScenarioDialogueView.dialogBtn` 仅在打字机播放期间启用并覆盖屏幕，点击后立即补完文本并禁用；文本自然完成时也禁用，瞬显文本不启用。
- 自动：`Auto_Time`
- 自动：`Auto_Time >= 0` 启用倒计时；主动点击会统一推进并取消当前倒计时
- 音频/效果：`Voice_Asset` 步骤出现时播放；`Effect_Asset` 实例化到 Binder 的 `effect` 节点并应用 `Effect_Offset`；`Shake_Time` 为震屏时长，单位毫秒，`<=0` 不震屏。
- **停止控制：`Next_ActionStop`（1结束引导，0继续下一步）**

---

## 4. 运行时主流程（现状）

```text
TryPlayForLevelEntry(level, hadAnyLevelDataBeforeLoad, hadCurrentLevelDataBeforeLoad)
  -> 先恢复 GameGuideState 中未完成的 Segment
  -> 再按 GuideScenarioTriggerConfig 判断当前关卡首次进入条件
  -> PlaySegment(segmentId)
  -> LoadSteps() [ConfigManager]
  -> ValidateSteps()
  -> SegmentID 过滤 + Sequence 排序
  -> 从最后完成 Sequence 之后的步骤开始
  -> EnsureRootView()  // UIManager.Open，已打开则复用
  -> MoveNextStep()    // 背景变化时 0.2s 淡出/刷新/淡入，否则瞬间换步

步骤完成推进条件后：
  -> AdvanceOrStop(step)
     - 当前步骤为终止步骤或最后一步 -> PersistSegmentProgress -> StopSegment() -> Close(true)
     - 其余情况 -> PersistSegmentProgress(当前步骤) -> MoveNextStep()（不关窗）

进度语义：
- 引导开始写入 `0`，用于标记已开始但尚未完成的段落。
- 每次推进前保存当前步骤 Sequence；中途退出时下次从该步骤之后继续。
- 仅保存到该 Segment 的最大 Sequence 才会跳过后续触发。
```

推进方式：
- FullScreenClick：打字中先补完，打字完成后触发推进
- TargetClick：命中挖洞区域后推进，且点击会同时传递给洞内底层 UI
- Auto：`Auto_Time` 倒计时结束后推进

> 点击与自动推进最终都汇总到 `AdvanceStep`，因此完成处理与 `Next_ActionStop` 行为一致。

---

## 5. 对外调用

```csharp
GuideScenarioManager.Instance.PlaySegment("NEWGUY");
GuideScenarioManager.Instance.TryPlayForLevelEntry(level, hadAnyLevelDataBeforeLoad,
    hadCurrentLevelDataBeforeLoad);
GuideScenarioManager.Instance.StopSegment();
GuideScenarioManager.Instance.SetSegmentProgress("NEWGUY", 3);
var step = GuideScenarioManager.Instance.GetCurrentStep();
bool playing = GuideScenarioManager.Instance.IsPlaying;
```

### 5.1 编辑器测试入口

选中场景中的 `GuideScenarioManager`，可在 Inspector 使用：

- `按配置测试引导`：选择 `测试段落` 并填写 `测试序号`，按配置处理点击或自动推进；
- `测试下一步`：忽略当前步骤的完成条件，直接刷新下一步；
- `强制关闭引导`：立即关闭当前引导，方便修改配置后重新测试；
- `测试段落`：指定测试使用的 `SegmentID`，默认 `NEWGUY`。
- Inspector 会显示当前运行中的 `SegmentID` 和 `Sequence`；不再提供单独的“跳转到引导步骤”按钮。

这些入口只用于测试表现，不写入引导完成进度。

---

## 6. 已知待办（保留）

- `Effect_Time` 暂按步骤出现时处理，后续再扩展时机
- Editor 拖拽回写配置未完成
- 多配置集组合（guide1/guide2）未实现

---

## 7. 快速定位

- 播放入口：`GuideScenarioManager.PlaySegment`
- 开窗常驻 / 瞬间换步：`EnsureRootView` + `GuideScenarioRootView.Refresh`
- 停止分流与完成落盘：`GuideScenarioManager.AdvanceOrStop`
- 手动设置进度：`GuideScenarioManager.SetSegmentProgress`
- 推进判定：`GuideScenarioAdvanceResolver`
- 对话 Speaker：`GuideScenarioDialogueView.ApplySpeakerSide`（由 `Avatar_Position` 驱动）
- 配置读取：`GuideScenarioConfigRepository.LoadSteps` -> `ConfigManager.GetGuide_ScenarioList`
- 配置模型：`Assets/GameModule/GameDataConfig/Config/GuideScenario/Scripts/GuideScenario.cs`
- GuideModule 兼容扩展：`Assets/GameModule/GuideModule/Script/Core/Guide_Scenario.cs`
