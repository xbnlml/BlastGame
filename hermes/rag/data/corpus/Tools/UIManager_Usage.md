# UIManager Usage

> **AI 使用提示**：处理窗口打开/关闭、遮罩点击、UI 动画或 UIManager 生命周期时读取本文；先复用现有窗口链路，再修改具体 View。

## Mask click control

`UIWindowConfig.maskClickEnabled` controls whether the current window's mask accepts clicks. It defaults to `true`. Set it to `false` before starting an external animation or custom timed operation, then set it back to `true` in the completion callback to restore mask interaction without changing the `UIManager` open/close flow.

```csharp
var window = UIManager.Instance.Open<MyWindow>();
window.UIWindowConfig.maskClickEnabled = false;

PlayCustomAnimation(() => window.UIWindowConfig.maskClickEnabled = true);
```

本文记录项目当前 UI 框架的基础链路与窗口动效约定，作为 `UIManager` 总文档使用。

## 0. 项目 UI 基线（Blast）

- **形态**：竖版手游；UI 为纯 UI 工程，统一走 Betta `UIManager` 一套体系（无第二套 UI 框架）。
- **设计分辨率**：`1080 × 2340`（`Resources/ScreenResolutionAsset.asset` 中 Portrait 方向 `canvasSize`；横屏条目为 `2340 × 1080` 备用）。
- **Canvas 渲染**：`Screen Space - Camera`；`UICanvas.Init` 绑定 `UIManager.uiCamera`，`planeDistance = 10`。
- **多 Canvas 分层**：按 `UIWindowConfig.layerOrder`（即 Canvas `sortingOrder`）懒创建多个 `UICanvas`；默认层 `UIDefine.UISortingOrderDefault = 100`。窗口预制体只需配置 `layerOrder`，不要为层级再叠一层全屏 Canvas。
- **缩放适配**：`CanvasScaler.ScaleWithScreenSize` + `referenceResolution` 来自 `ScreenResolution`；`UICanvas` 在 `Awake` 和 `Init` 都会刷新一次适配。非 iPad 设备按宽高比分段插值（长屏 `match = 0.25`，短屏 `match = 0.95`，中间线性过渡），iPad 使用单独分段（竖屏 `0.75`、横屏 `0.35`）。
- **窗口遮罩**：全局单例 `UIWindowBg`（`Resources/UIWindowBg`）由 `UIManager` 按当前顶部窗口刷新。`Normal` / `AutoClose` 时，遮罩挂到窗口所在 Canvas，并排列在窗口的前一个 sibling；`None` 表示窗口自行管理遮罩，通用遮罩隐藏。`AutoClose` 继续按 `maskClickEnabled` 决定点击遮罩是否关闭当前窗口。
- **Blast 业务分层**（见下文 §2.4）：
  - **界面 / 弹窗**：`BlastUIWindowView<TBinder>` + 预制体根上的 `*ViewBinder`；`UIManager.Open<T>()` 负责加载与生命周期。
  - **窗口内由 `UIBase.CreateCell` 管理的子块**：`BlastUIBaseView<TBinder>`（仍走 `UIBase`，但不经 `UIManager` 窗口栈）。
  - **列表格、奖励格等小 Item**：普通 `MonoBehaviour`（如 `RewardItem`），挂在 Prefab 子节点上，由父 View 调用 `Refresh` / `Hide`，**不**继承 `UIWindow` / `BlastUIWindowView`。

详细 SDK 说明见 `Assets/Betta/BettaSDK_UI_Resource_Manual.md` 第一、二章。

## 1. 代码范围

- Betta：`Assets/Betta/Scripts/Runtime/UIManager/`（`UIBase` / `UIWindow` / `UIManager` / `UICanvas` / `UIWindowBg`）
- Blast 窗口层：`Assets/GameModule/GameMain/Script/UI/BlastUIWindowView.cs`
- Blast Binder：`Assets/GameModule/GameMain/Script/UI/ViewBinder/BlastViewBinderBase.cs`
- Blast 子块（Cell）：`Assets/GameModule/GameMain/Script/UI/BlastUIBaseView.cs`
- 小 Item 示例：`Assets/GameModule/Common/Script/UI/RewardItem.cs`

## 2. UI 基础链路

### 2.1 UIBase

- 负责通用 UI 生命周期：`OnAwake` -> `OnInit` -> `OnUpdate` -> `OnDestroy`。
- 通过 `AssetPath` 加载预制体（优先 `ResourceHub`，回退 `Resources`）。
- 管理 cell 子视图：`CreateCell` / `CreateCellWithObj` / `DestroyCell`。

### 2.2 UIWindow

- 继承 `UIBase`，补充窗口层逻辑。
- `OnAwake` 中保证 `UIWindowConfig` 存在，并按 `layerOrder` 挂到对应 `UICanvas`。
- `OnFocus(bool focus)` 统一派发 `MessageType.OnWindowFocus`。
- `Close(bool force = false)` 作为窗口统一关闭入口，支持强制关闭参数。

### 2.3 UIManager

- 维护窗口栈：`Open<T>()` / `Close<T>()` / `Close(UIWindow)` / `CloseAll()`。
- `Open<T>()`：
  - 已存在窗口则置顶返回；
  - 新建窗口后加入 `_windows`，并处理背景遮罩与焦点切换。
- `Close<T>()`：
  - 先拿到窗口实例，再调用 `win.Close()`，确保不会绕过窗口自身关闭流程。
- `Close(UIWindow)`：
  - 负责最终销毁、焦点回切、关闭消息派发（最终关闭通道）。

### 2.4 Blast 业务 UI 分层

| 层级 | 基类 | 组件绑定 | 谁管生命周期 |
|------|------|----------|----------------|
| 界面 / 弹窗 | `BlastUIWindowView<TBinder> : UIWindow` | 预制体根节点挂 `TBinder`（继承 `BlastViewBinderBase`），`OnInit` 里 `RectTransform.GetComponent<TBinder>()` | `UIManager.Open<T>()` / `Close()`：加载 `AssetPath`、挂 `UICanvas`、遮罩、焦点 |
| 窗口内子块（Cell） | `BlastUIBaseView<TBinder> : UIBase` | 同上，由 `CreateCell` 传入已有 `RectTransform` | 父 `UIBase` 的 `CreateCell` / `DestroyCell` |
| 小 Item / 格子 | `MonoBehaviour`（如 `RewardItem`） | `public` 字段在 Inspector 拖引用，或子类自行 `[SerializeField]` | **父 View** 在 `OnInit` / 列表回调里 `GetComponent` 或序列化引用后调用 `Refresh` / `Hide` |

约定：

- **新界面**：逻辑类继承 `BlastUIWindowView<XXXViewBinder>`，预制体根挂 `XXXViewBinder`（按钮、文本、ScrollView 等引用只放在 Binder 上）；逻辑里用 `Binder.xxx` 访问组件，在 `BindEvents` / `UnbindEvents` 里注册/注销点击。
- **不要**让小 Item 也走 `UIManager.Open`；它们不是窗口，没有 `UIWindowConfig` / 遮罩栈。
- Binder 上必绑组件在代码里**直接访问**（不做 null 兼容），见 `.cursor/rules/ui-no-component-null-guard.mdc`。
- **Prefab 脚本生成**（`Assets/GameModule/**/*.prefab`）：
  - `Assets/GameModule/Create UI View Scripts`：同时生成 View + Binder（`PrefabUIViewGeneratorMenu`）
  - `Assets/GameModule/Create UI Binder Script`：仅生成 / 覆盖 Binder，不改 View（`PrefabUIBinderGeneratorMenu`）
  - 共享核心：`PrefabUIScriptGeneratorCore`；Tools 菜单同名入口在 `Tools/GameModule/`

典型打开方式：

```csharp
UIManager.Instance.Open<UIProfileView>();
```

`BlastUIWindowView` 打开顺序（在 `UIBase` 加载完预制体之后）：取 `Binder` → `OnInit` → 播放入场动画 → `BindEvents` → `OnShowed`。

说明：`BindEvents` 在入场动画完成后再执行，避免动画期间误点；`UnbindEvents` 仍在 `OnClose`。需要「动画后再做事」时重写 `OnShowed` 即可。

## 3. BlastUIWindowView 基础能力

- `BlastUIWindowView<TBinder>` 是**所有 Blast 窗口**的适配基类（`TBinder : BlastViewBinderBase`）：
  - `TBinder` 挂在窗口预制体根上，集中暴露 UI 组件与 `AnimationMode`
  - `BindEvents`：入场动画完成后注册；`UnbindEvents`：在 `OnClose` 注销
  - `Close()` / `Close(true)`：立刻 `OnHidden` 后销毁（不播退场动画）
  - `Close(false)`：先播退场动画，再 `OnHidden` → `UIManager.Close(this)`
  - **退场点击屏蔽（默认开）**：`Close(false)` 开播前将根节点 `CanvasGroup.interactable = false`，挡住本窗全部按钮；子类 `override BlockClicksDuringCloseAnimation => false` 可关闭
- `BlastViewBinderBase`：仅 `MonoBehaviour`，负责 Inspector 引用与窗口动画模式枚举，**不写业务逻辑**。

## 4. 窗口动画约定（DOTween）

### 4.1 默认行为

- 动画模式在 Prefab 的 `BlastViewBinderBase.AnimationMode` 上配置。
- 模式枚举：`None | Fade | Scale | FadeScale | Animator | Timeline | CommonAnimator`（`BlastWindowAnimMode`）
- View 侧可重写参数：
  - `ShowDuration`
  - `HideDuration`
  - `ShowFromScale`
  - `HideToScale`
- View 侧可重写动画入口：
  - `TryPlayCustomShowAnimation(Action onCompleted)`：用 Animator、Timeline 等非 Tween 系统接管入场，完成时调用回调并返回 `true`。
  - `CreateShowTween()`：用 Tween 自定义入场动画。
  - `PlayIdleAnimation()`：入场完成后启动循环或待机动画。
  - `TryPlayCustomCloseAnimation(Action onCompleted)`：用 Animator、Timeline 等非 Tween 系统接管退场，完成时调用回调并返回 `true`。
  - `CreateCloseTween()`：用 Tween 自定义退场动画。
- 自定义动画入口不依赖 `AnimationMode`；窗口可将 Binder 的 `AnimationMode` 保持为 `None`，由自身完全接管 Show/Idle/Close。

### 4.3 Animator / Timeline 命名约定

- `BlastViewBinderBase.AnimationMode`：`None | Fade | Scale | FadeScale | Animator | Timeline | CommonAnimator`。
- Animator 类型查找窗口子树中包含约定 Clip/State 的 Animator，名称为：
  - `Ani_{PrefabName}_appear`
  - `Ani_{PrefabName}_idle`
  - `Ani_{PrefabName}_close`
- CommonAnimator 类型使用跨窗口共用的固定命名：窗口下必须有节点 `Ani_Root_Common`，且其上必须挂 `Animator`；状态名为：
  - `Ani_Root_Common_appear`
  - `Ani_Root_Common_idle`
  - `Ani_Root_Common_close`
- Timeline 类型查找窗口下名为：
  - `Tim_{PrefabName}_appear`
  - `Tim_{PrefabName}_idle`
  - `Tim_{PrefabName}_close`
- 资源缺失口径按阶段区分：`appear` / `idle` 找不到节点、Animator、State 或 playable 时抛 `MissingComponentException` 暴露问题；`close`（含子类 `close1` / `close2` / `close1_0X` 等 `close` 前缀阶段）找不到时不报错，退回默认 tween 直接收窗。
- Animator / CommonAnimator 的 appear/close 动画由 `AnimatorManager.PlayAnimator` 按目标状态的 clip 时长触发完成回调，不需要配置 Animation Event。
- Timeline 的 appear/close 通过 `PlayableDirector.stopped` 完成生命周期回调，idle 使用循环播放；窗口 Timeline 结束模式为 `None`，不按时长推断动画完成。

### 4.2 生命周期

- `OnInit()`：窗口打开时立刻执行（取 Binder、准备数据等）。
- `OnShowed()`：显示动画完成后触发（此时 `BindEvents` 已执行）。
- `OnHidden()`：真正销毁前触发。
- `BindEvents`：入场动画完成后再注册点击/数据事件；`UnbindEvents` 在 `OnClose`。

### 4.3 关闭时序

1. 动画关闭：`Close(false)` ->（默认）`CanvasGroup.interactable=false` -> 播放隐藏动画 -> `OnHidden()` -> `UIManager.Close(this)`。
2. 立刻关闭：`Close()` / `Close(true)` -> 跳过动画 -> `OnHidden()` -> `UIManager.Close(this)`（不走点击屏蔽）。
3. 子类关闭屏蔽：`protected override bool BlockClicksDuringCloseAnimation => false`。

## 5. ScrollView 窗口建议

- 默认建议使用 `Fade`，避免缩放影响列表尺寸计算。
- 若业务必须使用 `Scale/FadeScale`，把依赖稳定布局的列表初始化/刷新放到 `OnShowed()`。

示例：

```csharp
protected override void OnShowed()
{
    // 动画结束后初始化或刷新 ScrollView 数据
}
```
