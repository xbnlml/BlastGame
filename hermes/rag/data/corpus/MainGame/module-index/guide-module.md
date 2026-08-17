# GuideModule 模块代码导航

- 模块目录：`Assets/GameModule/GuideModule/`

## 模块定位

- 引导/剧情模块。
- 实现文档：`Doc/GuideModule/GuideModule_Implementation.md`
- 步骤配置源：`Assets/GameModule/GameDataConfig/Config/GuideScenario/Data/guidescenario.bytes`
- 触发配置：`GuideScenarioTriggerConfig`（关卡首次进入与前置 Segment）

## 快速定位（关键词 → 类/方法）

| 关键词 / 问题 | 类 | 方法 / 关注点 | 路径 |
|---|---|---|---|
| 引导 / 剧情 / 新手引导 | `GuideScenarioManager` | `TryPlayForLevelEntry` / `PlaySegment` / `StopSegment`（`UIManager.Open` 常驻） | `Script/Runtime/GuideScenarioManager.cs` |
| 引导界面测试 | `GuideScenarioManager` | Inspector：先确认 `启用引导弹窗逻辑`，再选择 `测试段落`、填写 `测试序号`；测试不存档，支持 `强制关闭引导` | `Script/Runtime/GuideScenarioManager.cs` |
| 引导会话状态 | `GuideScenarioSession` | 会话容器 | `Script/Runtime/GuideScenarioSession.cs` |
| 步骤推进 / 点击推进 | `GuideScenarioAdvanceResolver` | `Auto_Time` 控制自动推进，点击与自动统一推进 | `Script/Runtime/GuideScenarioAdvanceResolver.cs` |
| 引导目标 / 挖洞命中 | `GuideScenarioMaskHoleView` | 按挖洞区域判断命中，不再读取 `Target_Position` | `Script/UI/GuideScenarioMaskHoleView.cs` |
| 引导窗体 / Binder / 淡入淡出 | `GuideScenarioRootView` / `GuideScenarioRootViewBinder` | `TransitionTo` / `effect` 节点 | `Script/UI/` + `ViewBinder/` |
| 打字机 / 对话 / Speaker | `GuideScenarioDialogueView` / `GuideTypewriterPlayer` | `Avatar_Position` 驱动左右 Speaker | `Script/UI/` |
| 手势引导 | `GuideScenarioHandView` | `Hand_Type` 切换 Hand/Arrow，应用偏移和旋转 | `Script/UI/GuideScenarioHandView.cs` |
| 挖洞遮罩 | `GuideScenarioMaskHoleView` + `UiInverseTextureMask` | `BG_Mask_Type` 切换圆形/矩形，`BG_Mask_Size` 配置位置和尺寸 | `Script/UI/GuideScenarioMaskHoleView.cs` |
| 引导配置 / json | `GuideScenarioConfigRepository` | 读写配置 | `Script/Core/GuideScenarioConfigRepository.cs` |
| 引导编辑器 | `GuideScenarioEditorWindow` | Odin + UI Toolkit | `Editor/GuideScenarioEditorWindow.cs` |

## 入口类（简注）

| 类名 | 适用场景（简注） | 路径 |
|---|---|---|
| `GuideScenarioManager` | 引导流程总控入口（启停与推进） | `Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioManager.cs` |
| `GuideScenarioSession` | 引导会话状态容器 | `Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioSession.cs` |
| `GuideScenarioTargetResolver` | 引导目标定位与命中判定 | `Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioTargetResolver.cs` |
| `GuideScenarioRootView` | 引导总控窗体（`BlastUIWindowView`，`Refresh` 瞬间换步） | `Assets/GameModule/GuideModule/Script/UI/GuideScenarioRootView.cs` |

## Model 类

- 暂无 `*Model` 命名类。

## UI*View 类

- 暂无 `UI*View` 命名类。

## 详细索引（迁移自旧总文档）

## GuideModule（引导/剧情系统）

> 模块路径：`Assets/GameModule/GuideModule/`；步骤配置源：`Assets/GameModule/GameDataConfig/Config/GuideScenario/Data/guidescenario.bytes`；触发配置：`GuideScenarioTriggerConfig`
> 实现文档：`Doc/GuideModule/GuideModule_Implementation.md`

### Core（配置与枚举）

- `GuideScenarioStepRecord` — 步骤数据模型，偏移字段 string→parse。`Assets/GameModule/GuideModule/Script/Core/GuideScenarioStepRecord.cs`
- `GuideScenarioConfigRepository` — json 读写。`Assets/GameModule/GuideModule/Script/Core/GuideScenarioConfigRepository.cs`
- `GuideScenarioConfigValidator` — 配置校验。`Assets/GameModule/GuideModule/Script/Core/GuideScenarioConfigValidator.cs`
- `GuideScenarioTriggerConfig` — 首次进入触发关卡映射与前置条件。`Assets/GameModule/GuideModule/Script/Core/GuideScenarioTriggerConfig.cs`
- `GuideScenarioEnums` — 枚举 + GuideOffset + GuideOffsetParser。`Assets/GameModule/GuideModule/Script/Core/GuideScenarioEnums.cs`

### Runtime（运行时）

- `GuideScenarioManager` — SingletonMono 单例入口，负责首次进入触发、未完成段恢复、`UIManager` 开窗常驻、步骤瞬间 Refresh、结束 Close。`Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioManager.cs`
- `GuideScenarioSession` — 会话状态容器。`Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioSession.cs`
- `GuideScenarioAdvanceResolver` — 推进模式判定。`Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioAdvanceResolver.cs`
- `GuideScenarioTargetResolver` — 目标位置解析/命中判定。`Assets/GameModule/GuideModule/Script/Runtime/GuideScenarioTargetResolver.cs`

### UI（视图）

- `GuideScenarioRootView` — `BlastUIWindowView` 总控窗体，开窗常驻 + `Refresh` 瞬间换步。`Assets/GameModule/GuideModule/Script/UI/GuideScenarioRootView.cs`
- 引导特效 — 配置 `Effect_Asset` 只填写预设名，运行时从 `Assets/GameModule/GuideModule/Prefabs/` 加载并挂到 Binder 的 `effect` 节点。
- `GuideScenarioRootViewBinder` — RootView 组件绑定（`AnimationMode=None`）。`Assets/GameModule/GuideModule/Script/UI/ViewBinder/GuideScenarioRootViewBinder.cs`
- `GuideScenarioCharacterView` — 角色显示；静态图仅在角色首次加载或切换时播放 OutBack 入场缩放。`Assets/GameModule/GuideModule/Script/UI/GuideScenarioCharacterView.cs`
- `GuideScenarioDialogueView` — DialoguePanel + 左右 Speaker + 打字机；`Adaptation=1` 时隐藏对话框并由 RootView 从 `GuideModule/Prefabs/` 加载 `Character` 预设到 `prefabPanel`。`Assets/GameModule/GuideModule/Script/UI/GuideScenarioDialogueView.cs`
- `GuideScenarioManager.NoticeNextGuide()` — 通用业务事件推进入口，由外部成功事件直接调用。
- `GuideTypewriterPlayer` — 通用 TMP 打字机。`Assets/GameModule/GuideModule/Script/UI/GuideTypewriterPlayer.cs`
- `GuideScenarioHandView` — 手势指示。`Assets/GameModule/GuideModule/Script/UI/GuideScenarioHandView.cs`
- `GuideScenarioMaskHoleView` — 挖洞遮罩（四节点绑定，按 `BG_Mask_Type` 切换圆形/矩形；`BG_Mask_Size` 两项依次为位置与宽高）。`Assets/GameModule/GuideModule/Script/UI/GuideScenarioMaskHoleView.cs`
- `Vibrate_Time` — 步骤出现时作为 Haptic Catalog ID 播放；`-1` 不播放。`Assets/GameModule/GuideModule/Script/UI/GuideScenarioRootView.cs`

### Editor（编辑器）

- `GuideScenarioEditorWindow` — Odin+UI Toolkit 编辑器。`Assets/GameModule/GuideModule/Editor/GuideScenarioEditorWindow.cs`
- `GuideScenarioEditorState` — 编辑态数据。`Assets/GameModule/GuideModule/Editor/GuideScenarioEditorState.cs`
- `GuideScenarioEditorSerializer` — 保存/复原。`Assets/GameModule/GuideModule/Editor/GuideScenarioEditorSerializer.cs`
- `GuideScenarioPreviewController` — 预览面板。`Assets/GameModule/GuideModule/Editor/GuideScenarioPreviewController.cs`
- `GuideScenarioPreviewPreset` — 预览预设 SO。`Assets/GameModule/GuideModule/Editor/GuideScenarioPreviewPreset.cs`

## 返回主入口

- [GameModule 多 Agent 代码导航总纲](../gamemain-class-function-index.md)
