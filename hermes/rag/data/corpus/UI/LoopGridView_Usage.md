# LoopGridView 使用文档

## 概述

`LoopGridView` 是 SuperScrollView 插件提供的网格循环列表组件（`Assets/Plugins/ThirdSdk/SuperScrollView/Scripts/GridView/LoopGridView.cs`），相比 `LoopListView2`，它以 Row/Column 二维坐标定位 item，适合网格布局场景。

在 GrandOpeningWeek 模块中用于 7 天每日签到列表（单列模式）。

## 与 LoopListView2 的关键差异

| 特性 | LoopListView2 | LoopGridView |
|------|---------------|--------------|
| 初始化 | `InitListView(count, onGetItemByIndex)` | `InitGridView(count, onGetItemByRowColumn)` |
| 回调签名 | `Func<LoopListView2, int, LoopListViewItem2>` | `Func<LoopGridView, int, int, LoopGridViewItem>` |
| 回调参数 | `(listView, index)` | `(gridView, row, column)` |
| Item 类型 | `LoopListViewItem2` | `LoopGridViewItem` |
| 列数控制 | 无（单列） | `GridFixedType.ColumnCountFixed` / `RowCountFixed` |

## 基本用法

### 1. 初始化

```csharp
// 单列 N 行模式
gridView.InitGridView(itemCount, OnGetItemByRowColumn);

// 带配置参数
gridView.InitGridView(
    itemCount,
    OnGetItemByRowColumn,
    initParam: LoopGridViewInitParam.CopyDefaultInitParam(),
    settingParam: new LoopGridViewSettingParam { mItemSize = new Vector2(200, 100) }
);
```

### 2. 回调实现

```csharp
private LoopGridViewItem OnGetItemByRowColumn(LoopGridView gridView, int row, int column)
{
    // row: 行索引 (0-based)
    // column: 列索引 (0-based), 单列时为 0
    var item = gridView.NewListViewItem("YourItemPrefabName");
    if (item == null) return null;

    var yourComponent = item.GetComponent<YourItemComponent>()
                     ?? item.GetComponentInChildren<YourItemComponent>(true);
    if (yourComponent == null) return item;

    yourComponent.Refresh(/* ... */);
    return item;
}
```

### 3. 刷新列表

```csharp
// 更新 item 数量（保持滚动位置）
gridView.SetListItemCount(newCount, resetPos: false);
gridView.RefreshAllShownItem();

// 强制检查可见区域
gridView.ForceToCheckContentPos();
```

### 4. 滚动到指定位置

```csharp
gridView.MovePanelToItemByRowColumn(row, column, offsetX: 0, offsetY: 0);
```

## 在 GrandOpeningWeek 中的应用

```csharp
// 7 天每日签到，单列 7 行
private const int DailyRewardDays = 7;

private void InitRewardList()
{
    if (!_isListInited)
    {
        Binder.RewardList.InitGridView(DailyRewardDays, OnGetItemByRowColumn);
        _isListInited = true;
    }
    else
    {
        Binder.RewardList.SetListItemCount(DailyRewardDays, false);
        Binder.RewardList.RefreshAllShownItem();
    }
}

private LoopGridViewItem OnGetItemByRowColumn(LoopGridView gridView, int row, int column)
{
    var day = row + 1; // 单列：day = row + 1
    var item = gridView.NewListViewItem("GrandOpeningWeekSignRewardItem");
    var signItem = item.GetComponent<GrandOpeningWeekSignRewardItem>();
    signItem.Refresh(state, day, rewards, onClaim, onResign);
    return item;
}
```

## 注意事项

1. **Prefab 注册**：Item prefab 需在 Unity Inspector 中拖入 LoopGridView 的 `Item Prefab Data List`，或通过代码 `GetItemPrefabConfData(prefabName)` 匹配。
2. **GridFixedType**：在预制体 Inspector 中设置 `ColumnCountFixed`（固定列数）或 `RowCountFixed`（固定行数），配合 `FixedRowOrColumnCount` 使用。
3. **NewListViewItem**：传入的 prefabName 需与 `StaggeredGridItemPrefabConfData` 中 prefab 名称匹配。
4. **性能**：与 LoopListView2 一样使用对象池复用，无需手动管理 item 创建与销毁。
5. **列索引计算**：单列场景 `column` 恒为 0，`day = row + 1`；多列场景需 `day = row * columnCount + column + 1`。

## 参考文件

- 源码：`Assets/Plugins/ThirdSdk/SuperScrollView/Scripts/GridView/LoopGridView.cs`
- Item 基类：`Assets/Plugins/ThirdSdk/SuperScrollView/Scripts/GridView/LoopGridViewItem.cs`
- 使用示例：`Assets/GameModule/GrandOpeningWeekModule/Script/UI/UIGrandOpeningWeekView.cs`
- Demo：`Assets/Plugins/ThirdSdk/SuperScrollView/Demo/Scripts/ViewDemo/GridView/`
