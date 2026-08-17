# SplitAtlases Usage

> **AI 使用提示**：处理 UI Sprite、图集整理或 `SplitAtlases` 菜单时读取本文；入口为 `Tools/GameModule/SplitAtlases`，涉及移动/删除资源前先确认目标。

## 入口与适用范围

- Unity 菜单：`Tools/GameModule/SplitAtlases`。
- 源码：`Assets/GameModule/Editor/SplitAtlasesWindow.cs`。
- 默认贴图目录：`Assets/GameModule/GamePassModule/Textures/UI`；也可选择具有对应模块 `Prefabs/` 的其他贴图目录。
- 用途：按 Prefab 直接引用整理 UI Sprite、识别共享与未引用资源、检查 SpriteAtlas 归属，并对后续新增资源执行增量规范检查。

## Split 划分标准

- 工具从所选贴图目录逐级向上寻找同模块 `Prefabs/`。
- 资源归属只使用 Prefab 的直接依赖。单一 Prefab 直接引用的纹理整理至 `<所选目录>/<界面前缀>/`；界面前缀移除开头 `UI` 与结尾 `View`，例如 `UIPassBuyView` 对应 `PassBuy/`。
- 嵌套 Prefab 产生的递归依赖只显示为“间接使用”，不参与目录归属和 Common 判定。例如 `UIPassView -> UIPassLoopRewards -> pass_dajiang` 中，`pass_dajiang` 归入 `PassLoopRewards/`，`UIPassView` 仅列为间接使用者。
- 仅当纹理被两个或更多 Prefab 直接引用时才视为共享。共享图集边长估算公式为 `NextPowerOfTwo(max(最大单图边长, sqrt(总像素面积 * 1.10)))`：估算值 `>=1024` 时进入 `Common/`，小于 1024 时进入 `SharedSmall/`。

## 扫描结果

- 结果按 Prefab 分组；下拉三角展开该 Prefab 直接引用的 Sprite，`Locate` 可定位 Prefab。
- Sprite（无 Sprite 子资源时显示 Texture）可直接选中，`Copy Path` 可复制资源路径。
- “所属图集”列显示每张图片隶属的 SpriteAtlas。支持图集直接挂单图或挂文件夹；点击名称可定位图集，同图进入多个图集时可从菜单选择，未归入任何图集时显示“未加入图集”。
- 扫描结果底部以黄色列出未被当前模块 `Prefabs/` 直接或递归引用的纹理，表示仍可能由代码动态替换。点击资源可定位。
- “全项目搜索引用”批量检查 `Assets/` 下的直接资源依赖，并扫描 C# 中出现的资源名、路径或 GUID。找到资源或代码引用时保持黄色并返回可点击来源；两类引用均未发现时改为红色。取消搜索时不展示不完整结果。

## 执行整理

- 执行前可先扫描并导出 CSV；CSV 包含直接引用、间接使用、图集归属、尺寸和建议目录。
- 工具先一次性创建并刷新全部目标目录，再使用 `AssetDatabase.MoveAsset` 移动资源，保留 `.meta` GUID 和现有 Prefab 引用；目标路径已有同名资源时跳过并警告。
- 移动完成后，从最深层检查本次资源原目录，仅删除已经为空的旧目录及其 `.meta`；不会删除贴图根目录、目标目录或无关空目录。
- 执行后自动切换到窗口内日志页，不生成额外日志文件。“查看日志”显示当前会话最近一次日志，“返回扫描结果”回到资源列表。
- 日志包含移动数量、删除空目录数量、共享图集估算、图集归属、公用图片、直接引用、间接使用和未引用资源检查结果。

## 检查规范

“检查规范”页用于首次整理后的增量检查，复用同一套 Split 标准：

- 直接引用决定预期界面目录；共享资源按 `Common/SharedSmall` 划分。
- Sprite 必须位于预期目录。
- Sprite 只能属于一个当前模块 `Atlas/` 下的图集。
- 图集应以预期目录或该 Sprite 作为 packable。
- 无法确定引用归属的纹理作为异常提示人工确认。

检查结果只列出异常 Sprite，并显示实际问题与“对应标准”；Sprite 和实际图集均可点击定位。
