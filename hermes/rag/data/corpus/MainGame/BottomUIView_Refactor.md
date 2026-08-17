# BottomUIView 重构

## 文档定位

本文是 `BottomUIView` 重构的专题文档，记录底部导航栏的职责边界、页面切换规则、窗口显隐关系和重构检查项。

实现入口：

- `Assets/GameModule/HomeModule/Script/UI/BottomUIView.cs`
- `Assets/GameModule/HomeModule/Script/UI/ViewBinder/BottomUIViewBinder.cs`

## 当前职责

`BottomUIView` 负责 HomeModule 底部导航栏，不负责各业务页面内部逻辑。主要职责如下：

- 管理 Rank、Task、Home、Build、Card 五个导航页签。
- 维护当前页签 `_currentActiveTab`，默认页签为 `Home`。
- 按需打开对应窗口，并只显示当前页签对应的 HomeModule 窗口。
- 同步 TopUIView 与底部导航栏的显示状态。
- 在进入 `UIGameMainView` 时将底栏向下移动，离开时恢复显示位置。
- 维护选中态与未选中态按钮对象。
- 激活页签的选中按钮通过嵌套 `Canvas.overrideSorting` 置顶显示；取消激活后关闭 override，恢复原绘制顺序。不改 sibling，避免 `HorizontalLayoutGroup` 重排位置。

## 页签与窗口映射

| 页签 | 目标窗口 | 打开入口 | 当前显示条件 |
|---|---|---|---|
| `Rank` | `RankUIView` | `OpenRankWindow()` | 当前页签为 `Rank` |
| `Task` | `TaskUIView` | `OpenTaskWindow()` | 当前页签为 `Task` |
| `Home` | `UIHomeLevelView` | `OpenHomeWindow()` | 当前页签为 `Home` |
| `Build` | `CareerUIView` | `OpenBuildWindow()` | 当前页签为 `Build` |
| `Card` | `CollectUIView` | `OpenCardWindow()` | 当前页签为 `Card` |

页面切换统一经过 `SwitchToTab(string tabName)`，流程为：

1. 忽略重复点击当前页签。
2. 更新 `_currentActiveTab`。
3. 按需打开目标窗口。
4. 隐藏其他 HomeModule 页面。
5. 刷新按钮选中态。

## 生命周期与显隐

### 初始化

`OnInit()` 完成以下工作：

- 缓存底栏初始 anchored position。
- 打开并显示 Home 页签。
- 根据当前是否打开 `UIGameMainView`，同步底栏位置。

### 游戏关卡窗口

通过 `MessageType.OnWindowOpen` 和 `MessageType.OnWindowClose` 监听 `UIGameMainView`：

- 打开 `UIGameMainView`：隐藏 HomeModule 页面，并将底栏移动到隐藏位置。
- 关闭 `UIGameMainView`：恢复当前页签页面，并将底栏移动回初始位置。

底栏隐藏位移由 `HideOffsetY = -400f` 定义，动画时长统一读取 `ResolveBottomUiTweenDurationSeconds()`。

### 关闭与事件解绑

- `OnClose()` 必须停止所有 Tween。
- `UnbindEvents()` 必须移除窗口事件和全部按钮监听，避免重复绑定或对象销毁后的回调。

## Binder 约定

`BottomUIViewBinder` 只负责暴露 prefab 上的对象引用，不承载导航逻辑。每个页签包含：

- 一个选中态对象和一个未选中态对象。
- 一个选中态按钮和一个未选中态按钮。

当前页签的视觉切换由 `RefreshButtonVisuals()` 统一处理：先切换选中/未选中显隐，再调用 `UpdateActiveButtonHierarchy()`。层级规则为：

1. 导航按钮父节点 `Obj` 使用 `HorizontalLayoutGroup`，禁止通过改 sibling 置顶。
2. 激活页签的选中态对象添加/复用嵌套 `Canvas`，开启 `overrideSorting`，`sortingOrder` 取父级 Canvas 排序值 + 偏移。
3. 同步补齐 `GraphicRaycaster`，保证置顶后仍可点击。
4. 取消激活时关闭 `overrideSorting`，恢复原绘制顺序。

新增页签时，应同时补齐 Binder 字段、事件绑定、窗口打开、窗口显隐、按钮视觉状态，以及选中态置顶处理。

## 重构边界

### 应保留在 BottomUIView 的内容

- 页签状态管理。
- 导航按钮事件绑定与解绑。
- HomeModule 窗口的按需打开和互斥显隐。
- 底栏自身的位置动画与 Tween 生命周期。

### 不应下沉到 BottomUIView 的内容

- Rank、Task、Career、Collect、Home 页面内部业务逻辑。
- 体力、金币、任务、收集或关卡数据计算。
- prefab 资源加载细节。
- 具体页面的业务刷新策略。

## 重构检查项

- 页签名称、按钮对象、目标窗口和 `SetWindowVisible<T>` 的映射必须一一对应。
- `EnsureWindowOpened()` 的打开标记必须与实际窗口生命周期保持一致。
- 切换页签时，旧页面、`TopUIView` 和底栏按钮状态必须同步。
- `UIGameMainView` 打开和关闭时，底栏位置与页面显隐必须可恢复。
- 重复初始化、重复绑定、关闭后重新打开时，不得产生重复监听或残留 Tween。
- 所有动画时长应继续使用统一配置，不在组件内新增分散的魔法时长。
- 若新增或删除公共入口，同步更新 `home-module.md` 的快速定位表。

## 页面滑动动画与多分辨率适配

页签点击后的切换统一由 `SwitchHomeWindowWithSlide()` 处理：

- 根据 `Rank → Task → Home → Build → Card` 的顺序判断滑动方向。
- 新页面从目标方向进入，旧页面向相反方向退出；动画结束后再隐藏旧页面。
- 使用页面父级容器的实际宽度计算滑动距离，不使用固定屏幕宽度，兼容手机、Pad 和不同 Canvas 缩放。
- 滑动距离在实际宽度基础上增加 `TabSlideOverlap = 4f` 的重叠量，用于抵消浮点误差，避免切换过程中露出黑色缝隙。
- 当父级容器宽度不可用时，回退使用新旧页面的较大宽度。
- 切换前会停止未完成的上一次页面 Tween；关闭 `BottomUIView` 时同步清理页面切换 Tween。

Prefab 调整或新增页面时，应确保各页面使用同一套拉伸锚点，并挂在同一个可视区域父节点下；若父节点不是实际可视区域，应将页面移动到带 `RectMask2D` 的 Viewport 下，避免页面滑出时显示底层背景。

## 相关文件

- [HomeModule 模块索引](module-index/home-module.md)
- `Assets/GameModule/HomeModule/Script/UI/BottomUIView.cs`
- `Assets/GameModule/HomeModule/Script/UI/ViewBinder/BottomUIViewBinder.cs`
- `Assets/GameModule/HomeModule/Prefabs/BottomUIView.prefab`
