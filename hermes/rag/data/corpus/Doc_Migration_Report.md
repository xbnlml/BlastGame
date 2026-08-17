# Doc 文档维护与迁移报告

## 文档分层

| 层级 | 默认用途 | 内容边界 |
|---|---|---|
| 总入口 | 选择模块 | 只放入口、范围和下一步链接 |
| `module-index/` | 定位代码 | 关键词 → 类 / 方法 / 文件，不展开规则 |
| 专题文档 | 理解当前逻辑 | 职责、数据、流程、约束和排查入口 |
| `Tools/` | 使用工具 | 稳定命令、接入方式和限制 |
| `archive/` | 历史追溯 | 非当前真源，不进入默认导航 |

## 当前默认阅读路径

`关键词 → module-index → 单一专题 → 代码入口`

文档的主要价值是路由代码，不是复制代码实现。索引页只回答“去哪里看”，专题页只保留完整主流程、状态关系和关键边界；字段、动画参数、对象池细节和单次排障记录不属于默认阅读路径。

MainGame 从 [`MainGame 入口导航`](MainGame/Blast_MainGame.md) 开始；Bot 从 [`Bot & MainGame 文档导航`](Bot_MainGame_Doc_Navigation.md) 开始。

## 本次清理

已删除已落地、会误导当前实现的计划文档：

- MainGame 的 Controller / UI / Stage / Runtime 去重计划
- Bot 评分与 Runtime 仿真对齐计划
- GameModule、funnel、Token 使用优化计划
- 已声明“内容已合并”的 `Board_Cell_Animation_Playback.md`
- 已完成路由审计的临时 `Doc_Routing_Audit_Notes.md`
- 对应的计划归档占位文件

已将仍有效的规则保留在当前专题文档中，计划文件不再作为代码逻辑来源。

第二轮压缩了两个高频入口：

- `Doc/Bot/Bot_Architecture.md`：从过程日志改为当前分层、执行、策略、状态一致性和性能边界。
- `Doc/Bot/Bot_Execution_Logic_Unity.md`：删除按日期排列的修复记录，只保留 Unity 入口、参数契约、输出和验收。

## 当前真源约定

- 主流程：[`Gameplay_Flow_Logic.md`](MainGame/Gameplay_Flow_Logic.md)
- 玩法规则：[`Gameplay_Rules_Logic.md`](MainGame/Gameplay_Rules_Logic.md)
- 回放：[`Blast_Replay.md`](MainGame/Blast_Replay.md)
- 关卡进入：[`Level_Entry_Init_Logic.md`](MainGame/Level_Entry_Init_Logic.md)
- Board / Stage：[`GM_Board_Stage_Flow.md`](MainGame/GM_Board_Stage_Flow.md) 与 [`Stage_Animal_Animation_Playback.md`](MainGame/Stage_Animal_Animation_Playback.md)
- Bot 当前架构：[`Bot_Architecture.md`](Bot/Bot_Architecture.md)
- Bot 槽位状态对照：[`Bot_Runtime_Slot_State_Parity.md`](Bot/Bot_Runtime_Slot_State_Parity.md)

## 维护规则

- 当前文档不得保留已废弃类名、路径、状态机或配置口径。
- 归档文档不得加入关键词表、默认导航或专题常规入口。
- 已落地计划中的有效结论应合并到专题；计划本身删除。
- 新增规则只写入一个专题真源，索引页只写定位信息。
- 修改代码后按 `AgentRules/AGENT_RULES_DOC_SYNC.md` 同步对应专题。
- 新增内容前先判断它是否能帮助 AI 找到代码或理解主流程；仅描述实现细节、一次修改过程或实验结果的内容不写入当前文档。
