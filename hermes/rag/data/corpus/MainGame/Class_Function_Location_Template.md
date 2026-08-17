# Class Function Location 模板

用于在模块文档或专题索引页内维护“类功能定位”小节，便于快速按职责查代码。

## 使用方式

1. 在模块文档或细分索引页末尾新增 `## 类功能定位`。
2. 复制下方表格模板并填写“类/文件、功能、路径”。
3. 类职责变更、重命名或迁移时，同步更新本表与总索引文档。

## 模板（复制即用）

| 类/文件 | 功能 | 路径 |
|---|---|---|
| `ClassNameA` | 一句话描述职责（做什么，不写实现细节） | `Assets/.../ClassNameA.cs` |
| `ClassNameB` | 一句话描述职责（输入/输出或所在层） | `Assets/.../ClassNameB.cs` |
| `ClassNameC` | 一句话描述职责（与哪个模块协作） | `Assets/.../ClassNameC.cs` |

维护规则：新增/替换核心类时，优先更新本表，再更新 `Doc/MainGame/module-index/game-main-agent-index.md` 和对应细分页，必要时回写 `Doc/MainGame/gamemain-class-function-index.md` 总纲。
