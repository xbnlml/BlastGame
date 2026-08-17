# 工具/经验复用体系（2026-08-05 用户反复暴怒的核心问题）

> 用户最反复纠正的一件事：「为什么又是现有能用的工具却不用！！！！」「怎么彻底解决这个问题？」
> 根因不是内容缺失，是**检索/触发失效**——skill 里写了 gen_payload 9 次，动手时还是手写硬编码脚本。

## 两个不同的问题，两种解法

| | 经验/坑 | 工具/skill |
|---|---|---|
| 问题 | 忘了规则 | 不知道有现成工具 |
| 解法 | 踩坑→追加→自动加载（触发） | 可发现性（索引） |
| 关键 | 记忆触发 | 操作→工具映射表 |

## 高手的做法（关键洞察）

**高手不是建一个文件就完事，而是「踩坑→立刻追加进自动加载的小文件→下次触发」的闭环。**
> Matt Van Horn 22 条 Agentic Engineering：CLAUDE.md 是"持续编译的知识"，每次踩坑就追加，越厚越准。

- 闭环 = 踩坑 → 写进自动加载文件 → 下次会话必然看到 → 不犯
- 只能改善不能百分百根治，接受偶尔失误
- **别用 Claude Code 的名字**（用户纠正：我们是 Hermes），Hermes 用 `.hermes.md`

## Hermes 落地的三层体系

| 层 | 文件 | 作用 | 触发 |
|---|---|---|---|
| **工具索引** | `hermes/tools/README.md` | 操作→工具映射表（写操作/只读/判定/批跑/agent 五类）| `ls tools/` + 读 README |
| **自动加载守则** | `hermes/.hermes.md` | "动作前守则"，触发查 tools/README.md | **Hermes 每次会话自动注入**（git root 边界内）|
| **skill** | 全局 blastgame skill | 深度参考，按需加载 | skill_view |

**`.hermes.md` 是 Hermes 原生**（`_HERMES_MD_NAMES = (".hermes.md","HERMES.md")`，`_find_hermes_md` 从 cwd 向上到 git root 找，自动加载，20KB 上限）。这是"每次动手必触发"的根治方案，不依赖记得 skill_view。

## 动手前强制顺序（写进 .hermes.md + skill 顶部）

1. `ls tools/` + `ls project-state/` + `ls scripts/` + 读 `tools/README.md` —— 禁止一上来手写
2. 按"你想做什么"查工具：DB payload→`gen_payload.py --levels`（禁手写硬编码关卡列表脚本）、Excel→`write_tiers`、再asset→`write_ddc`、统一入库→`reimport.py`/`reimport_batch.py`
3. 判定/组合/探针 → 走现成只读脚本 `level_status.py`/`param_knowledge.py`/`find_best_combo.py`，别从零算
4. 改 asset 前先算 fingerprint（DB 可能已匹配，省 DB 写入）

## 通用教训（写"新东西"前这一刻最关键）

宁可多花 30 秒查工具，不写一行手写脚本。**一切不符合「先查」的动作都会被用户视为犯同样的错。** 本项目 34 个工具全部在 `tools/README.md` 记录，动手前必须扫。