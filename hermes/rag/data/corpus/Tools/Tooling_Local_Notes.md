# 本地工具使用约定

> **AI 使用提示**：需要选择本机工具入口时读取本文；工具优先级遵循 `AGENTS.md`，本文只提供可复用入口，不作为业务规则来源。

本文只记录当前仍可复用的工具入口；一次性排障命令、旧实验参数和历史过程不放在这里。

## 代码定位

- 代码查找和命令执行流程：遵循根目录 [`AGENTS.md`](../../AGENTS.md)。
- 本文只保留本机工具入口，不复制工具优先级和调用规则。
- 若工具索引不可用，直接使用项目文档和代码搜索，不阻塞任务。

## 常用工具入口

- 只读检查：`Tools/Python/GameTools/BlastCheckTool.py`
- 服务管理：`Tools/dev-services.sh status`
- 启动服务：`Tools/dev-services.sh start <service>`
- 关闭服务：`Tools/dev-services.sh stop <service>`
- Unity Editor 结构化查询与操作：`unity command <command>`；完整安装、连接和命令说明见 [`Unity_CLI_Pipeline.md`](Unity_CLI_Pipeline.md)。
- Unity 工具与 Editor 业务实现：按需查看 `Assets/GameModule/Editor/` 对应实现。
- 关卡中控 Hub：`Tools/Blast/关卡中控` 或 `Tools/level-editor`（`npm run dev` / launcher）。侧栏「数」关卡数据库 / 「配」配置对比；数据口径见 [`LevelDatabase/README.md`](../../LevelDatabase/README.md)，Run 使用关卡级 BoardFingerprint + 单条 DealFingerprint 双指纹。`funnel_b` 的 `lv_win_config` 目前仅 L1–50；数据库关卡组下拉在点「加载」前不会被轮询冲掉；无 Plan 但有 asset 时整行显示 diff，可用 asset 播种规划。

## 新增记录标准

只有满足以下条件才加入本文：

1. 当前流程仍使用。
2. 未来任务可能复用。
3. 能写清用途、入口、执行目录和最小示例。

稳定的重复检查应沉淀到 `Tools/Python/GameTools/BlastCheckTool.py`，本文只保留入口和限制。
