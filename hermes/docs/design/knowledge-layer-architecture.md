# BlastGame 知识分层架构方案（知识架构师输出）

> 日期：2026-08-14 · 用途：解决"知识文件分层混乱"（SKILL 166KB 超限、MEMORY 96% 满、references 有记录但检索不到、RAG 与 memory/skill 边界不清）
> 适用范围：全局权威位置 `C:\Users\Administrator\AppData\Local\hermes\`（skill+memory）+ 项目 `D:\download\BlastGame\hermes\`（tools/agents/RAG）

---

## 0. 现状盘点（实测数据）

| 层 | 现状 | 容量 |
|---|---|---|
| MEMORY.md（全局权威） | 74 条，34.5KB | 超限（20KB 预算 → 96% 满，实际已溢出） |
| USER.md（全局权威） | ~91 段，25.9KB | 超限，主题重复严重（"先展示再执行"类重复 8+ 次） |
| blastgame SKILL.md | 166.8KB | 严重超限（99.9KB→又涨到 166KB） |
| — 其中 常见坑速查 | 40.4KB（约 139 行坑表） | 单节占 1/4 |
| — 其中 References 大表 | 10.1KB（~60 行） | 与 INDEX.md 重复 |
| references/ | 119 个 md，640KB | INDEX.md 已建立（A-I 分组+2 周归档规则），但"有记录没被触发"仍在 |
| RAG（hermes/rag/） | 812 chunk，49 条 golden QA，BGE-small-zh-v1.5，BM25+向量混合 | recall@1=80%；语料只索引了 Doc/MainGame |
| agents/*/memory.md | 4 个 agent，共 13.9KB | 健康，勿动 |
| session_search | 全历史会话 | 只读检索，无容量问题 |

**核心矛盾**：所有"重要内容"都往 SKILL/MEMORY 塞（因为这两层被自动注入、最可靠），导致容量爆炸；references 有索引但发现路径靠"记得去看"，RAG 有语义检索却只装游戏文档。

---

## 1. 六层职责边界（一表定边界）

判断一个知识点去哪，先回答三个问题：
- **必须每次都在场吗？**（禁令/偏好/高频入口）→ MEMORY / USER / SKILL
- **是可检索的"机制知识"吗？**（how X works / 格式 / 公式）→ references + RAG
- **是历史事故或已定案案例吗？** → references（短期）→ 归档 → session_search

| 层 | 注入时机 | 放什么 | 不放什么 | 容量目标 |
|---|---|---|---|---|
| **USER.md** | 每次对话系统提示 | 用户身份、沟通/工作/学习偏好、职业目标、环境事实（路径/账号） | 项目技术规则、单次纠正记录 | ≤8KB |
| **MEMORY.md** | 每次对话系统提示 | ① 未落进 skill 的高危铁则 ② 当前生效的关键数值/真源 ③ 基础设施事实（路径/版本坑）④ 会被 bot400/DB 证伪的"易错认知"。**只放"不加载任何东西也不能忘"的 15-25 条** | 已写进 SKILL/references 的内容、单关案例、历史决策叙事 | ≤15KB（预算 20KB 内） |
| **SKILL.md** | 加载 skill 时注入 | 操作入口：前置条件/工具优先铁则/命令速查/判定速查表/流程速查/铁则 Top15/指针 | 大段明细（40KB 坑表）、案例复盘、重复 references 的全文 | 25-35KB |
| **references/** | 按需 skill_view（经 INDEX.md 定位） | 机制知识全文（公式/格式/流程/定稿）、审查报告、案例复盘（短期） | 已定稿且能进 RAG 的知识（留 INDEX 一行指针即可） | 单文件 ≤15KB，超则拆主题 |
| **RAG** | 按语义检索，只取相关 chunk | 定义性/机制性知识：游戏文档 + references 的"知识类"子集（DDA/DB/判定/探针机制） | 铁则、用户偏好、当前 board 状态、时效性未定稿决策、事故叙事 | 语料 ~1.5MB / 2000-3000 chunk |
| **session_search** | 按关键词搜历史会话 | 任何历史事实：具体 L### 事故全过程、已归档文件的原始上下文 | （无需主动写入，天然存在） | 无限 |

**agents/*/memory.md**：各 agent 自己的角色操作记忆（禁令/铁则/模式），与主 MEMORY 并列，不合并（注入时机不同：delegate 时才注入）。

**补充规则（防回潮）**：每次新知识落盘前先判层：禁令/偏好→MEMORY/USER；机制→references；可检索机制→同时 RAG 标记；事故→references（INDEX 标日期）→2 周后归档。写进 SKILL 使用规则里。

---

## 2. SKILL.md 瘦身方案（166KB → 约 30KB）

### 2.1 40KB「常见坑速查」去哪 —— 按主题拆 4 个文件

不整表搬（40KB 单文件按需加载也重），按主题拆，每个 ≤10KB，INDEX.md 登记：

| 新文件（references/pitfalls/） | 内容 | 估计 |
|---|---|---|
| `pitfalls-judgment.md` | 判定/分档/接近带/目标偏差/硬违规坑（现 #1,12,13,20,31,31b,36…） | ~10KB |
| `pitfalls-probe.md` | 探针设计坑（现 #3,21,22,24,33,34…） | ~8KB |
| `pitfalls-pipeline.md` | auto_loop/agent/轮次/JSON 解析坑（现 #4,10,14-19,25,26,28,39…） | ~10KB |
| `pitfalls-db-tooling.md` | DB/工具/Unity/路径坑（现 #5,27,29,30,37,38…） | ~12KB |

SKILL 内只保留 **Top-15「用户暴怒级」铁则**（如：工具优先、phase1/2 禁入库、禁 git 写操作、禁改 Unity 核心文件、Excel 唯一位置、全自动禁自动入库、探针禁跑已有配置、差≤5pp 不是改关卡…），一行一条 + 一行指针 `→ 完整坑表见 references/pitfalls/（按主题）`。
**净省 ~35KB。**

### 2.2 判定标准等内联大段 → 速查表 + 指针

判定标准下约 20 个子节（分档/容差/评分/硬违规/状态机…）在 references 里都有全文（judgment-rules/judgment-bands/judgment-tolerance/target-deviation/balanced-scoring/gap-surplus-scoring）。压缩成**一张速查表**（每行：项｜当前值｜裁决日期｜详情见哪）：
- 分档：≥70%→20 / 50-70%→15 / 30-50%→10 / <30%→6；接近带 15/10/7/4
- 合格容差 2pp、接近容差 1pp、目标偏差 max=10pp（硬）、FinalHardGate gap≤10+std≤2.5%
- 入库必须全绿 + 展示每档颜色表（≤10绿/10-15黄/>15红）让用户裁定
- E=1/WR 仅参考；6 轮状态机

数据可靠性/探针设计/Warden/入库落盘各节同理：每节保留 3-5 条速查要点 + 指针到对应 references。**净省 ~20KB。**

### 2.3 References 大表（10KB）→ 一行指针

SKILL 尾部 References 表与 references/INDEX.md 内容重复（INDEX 更新更全）。替换为：
`## References → 见 references/INDEX.md（A-I 主题索引；新 reference 必须登记）`
**净省 ~9KB。**

### 2.4 保留不动
前置条件、工具优先铁则、命令速查、只读查询命令、Agent 架构一行表。

### 2.5 执行方式
割出来用 `skill_manage(patch)` 逐段操作；坑表用脚本从 SKILL.md 抽出（139 行表格按主题分类）→ 写入新文件 → 在 INDEX.md 登记 → SKILL 内替换为铁则速查+指针。改完验证：`wc -c SKILL.md` 应在 30KB 上下。

---

## 3. MEMORY.md 清理标准（34.5KB/74 条 → ≤15KB/约 20 条）

### 3.1 四条删除/移动标准（按此筛每一条）

| 标准 | 判定问题 | 去向 |
|---|---|---|
| **D1 已落 skill/references** | 这条内容是否已写进 SKILL 或某 references 全文？ | 删，不留（需要时经 INDEX/RAG 取） |
| **D2 与 USER 重复** | 是沟通/工作/学习偏好、单次纠正的行为要求？ | 移到 USER（合并进同主题） |
| **D3 单关/单事件事故** | 是 L### 案例、某日某 bug 复盘？ | 删（references+session_search 已有） |
| **D4 已被新决策取代** | 是否被 08-12/13/14 更新版本覆盖？ | 删（保留最新版） |

**例外保留（四类必留）**：
- **高危铁则**（违规会触发用户暴怒且没写进 skill 或 skill 会漏加载的）：如"用户裁定权""黄区禁提改关卡""单批 bot400 不可当真值"
- **当前生效核心数值**：目标胜率定稿（151-200：normal 80/80/60/45/45 等）
- **真源/路径事实**：Excel 唯一位置、全局权威位置、课程文件位置、hermes config 坑
- **易错认知**（与直觉相反、bot400 会证伪的）：summary 入库会被 bot400 证伪、两套机制勿混

### 3.2 具体条目清点（74 条逐条归类，示例清单）

- **删（D1，已入 references）**：#3 asset 分段、#13 DDA 公式（→dda-runtime）、#30 数据源优先级（→source-parity）、#38 探针设计（→probe-efficiency）、#50 leveldb 三坑、#56/#60 牌面校验/时间防线（→pool-board-filter-final/mtime-fence）、#62 auto_loop 铁则（→auto-loop 系）、#92 判定 15→10（→judgment-green-standard）、#96 局数标准（→probe-games-standard）、#100/#106 探针对准（→probe-target-derivation）、#108 工具第四课（→tool-design-agent-ceiling）、#112/#120 bot400 一致性（→bot400-vs-db-consistency）、#124 write_level_db payload（→leveldb-import-white-tier）、#128 RAG 项目（→rag-tool-20260812）、#140 优化器 vs bot400（→optimizer-vs-bot-neutral-tier-rootcause）、#142 DB 导入（→leveldb-import-white-tier）、#148 防塌缩（→tier-collapse-*）…约 30 条
- **移（D2，→USER）**：#15 展示格式、#32 多 agent 协作、#64 工作流偏好、#70 根因分析、#98 用户关注点、#116/#118 学习偏好、#130 主动找文件、#134 素材分离…约 10 条
- **删（D3 单关/单事件）**：#80 08-07/08 综合、#86 08-09/10 细节、#88 备份偏好、#90 规范化、#110 L57 案例、#114 审美案例、#136 批次波动案例、#138 tool data 清空…约 12 条
- **压缩合并（同主题并成一条）**：#26 Unity 检查 / #5 / #37 同类工具坑合并；#52/#54/#82 入库记录规则合并成一条
- **保留**：#1 讨论模式、#5 来源时间、#7 Excel 真源、#11 全局权威、#19 git 规则、#24 Unity 核心文件、#28 phase1/2 禁入库、#44 多档 summary 例外、#48 Excel 位置、#74/#76 用户裁定权、#84 用户手动改 asset、#94 两套机制、#104 黄区禁改关卡、#112 一句"summary 会被证伪"、#126 课程位置、#144 目标胜率定稿、#146 hermes config 坑 → **约 18-20 条，~12-15KB**

### 3.3 执行
先备份 `MEMORY.md.bak` → 按上表重写（每条保留日期锚点 `2026-08-xx`）→ 检查 MEMORY+USER+SKILL 三处无信息丢失（每个删掉的条目确认其完整版在 references 可查）。

---

## 4. USER.md 清理（25.9KB → ≤8KB）

- **主题去重**（同一偏好出现 8+ 次的只留一句权威版）："先展示完整数据再下结论/不跳步"、"被纠正立刻承认不找借口"、"先方案后执行等确认"、"查全文件再动手不猜" → 各 1 条
- **保留**：身份背景、沟通/工作/学习偏好各 1 节（每节 5-8 行）、职业目标（压缩成 1 段：资深 AI 从业者/国内 AI 岗位/BlastGame 叙事/短板 RAG+Transformer/下一步 Transformer）、环境事实（GitHub 账号、项目路径、Apple ID、微信推送、RAG 学习已完成）
- **删**：过时的 cron 记录（每日一报/今日一课已删 2 次，留最后状态即可）、已完成待办（Skill 待办）、重复的课程进度记录（进度已被 08-13 状态覆盖）
- **移出**：项目技术规则（Excel 解析 1.0=100%、asset_patcher validate、Normal dedup、gap 判定规则）→ 这些不是"用户画像"，属 SKILL/references，USER 只留"用户要求展示局数/来源"类偏好

---

## 5. RAG 扩语料建议

### 5.1 结论：要扩，把 references 的「知识类」子集 + 游戏文档 Bot/Tools 加进去

**理由**：references"有记录但没被触发"的本质是**发现路径失效**——靠 INDEX.md 人工定位不可靠。RAG 按语义检索正好根治这个问题（问"DB 怎么同步"直接命中 leveldb 文档，不用记得文件名）。这是投入产出比最高的一步。

### 5.2 哪些 references 进 RAG（"知识类"标准）

判定标准：**"一个新工程师问'X 是怎么工作的'时需要它" → 进；"只在调试某次具体事故时需要它" → 不进**。

| 进 RAG（机制知识，定稿且不再变） | 不进 RAG（事故/叙事/历史） |
|---|---|
| dda-runtime.md、judgment-rules.md、difficulty-target-design-20260813、level-database-20260804、level-db-display-logic、level-database-run-write、leveldb-single-tier-write、leveldb-compare-match、leveldb-import-white-tier-20260813、probe-efficiency-standards-20260806、probe-target-derivation、tool-design-agent-ceiling、param-knowledge-20260803、optimizer-vs-bot-neutral-tier-rootcause、bot400-vs-db-consistency、rag-tool-20260812、auto-loop.md、agent-workflow.md、warden-gate.md、bot-submit-guard.md、pool-data-integrity.md、session-workstyle…（约 25-35 个） | l57-probe-exhaustion-case、l124-optimizer-case、L172-*、fixes-20260803*、auto-loop-timeout-chain、level-signature-check-reverted、project-audit、workflow-audit、role-architecture、各修复批次（这些留 references + 2 周后归档，真源=session_search） |

> ⚠️ **铁则绝不放 RAG**：MEMORY/SKILL 里的禁令（phase1/2 禁入库、禁 git 写、Excel 位置…）语义检索会拿"相似但已被取代"的旧版赢过"最新版"，风险高收益零。RAG 只装"知识"不装"规则"——这与用户已定的"AGENTS.md 宪法层绝不进 RAG"原则一致。

**防旧数据污染**：INDEX.md 加一列 `RAG`（✓/—），只标 ✓ 的进语料；INDEX 的"2 周归档规则"对 RAG 语料是硬闸门——归档的 reference 必须同步从 RAG 语料移除并重建索引。

### 5.3 怎么加 + 索引重建（具体步骤）

1. **配置**（`rag/config.py` 或环境变量，不硬编码）：
   - `RAG_CORPUS_SUBDIRS=MainGame,Bot,Tools`（游戏文档，已验证 928 chunk 时效果更好）
   - 新增第二个语料根：`RAG_KNOWLEDGE_ROOT` 指向 skill references（或复制一份 `hermes/rag/data/knowledge/`，只含 INDEX 标 ✓ 的文件，避免 build 时扫到事故文档）
2. **改 build_index.py**：`chunk_corpus()` 合并两个语料根的结果（chunk 的 `source` 带命名空间前缀如 `knowledge/xxx.md` vs `Doc/MainGame/xxx.md`，检索结果可区分来源）
3. **重建**：`python -m rag.build_index`（CPU 全量重建即可：现 812 chunk 秒级；加 ~35 个 reference + Bot/Tools ≈ 2000-3000 chunk，仍秒级。metadata.jsonl 已存内容 hash，可用来做变更检测/去重，但当前全量重建成本极低，无需增量）
4. **评估**：`python -m rag.eval --qa rag/data/golden_qa.json`（用 python 3.11 venv），golden QA 从 49 条扩到 ~70 条（补 15-20 条流水线机制题：DB 同步/探针反推/牌面校验/入库四动作…），对比扩语料前后 recall@1
5. **检索入口不变**：`python rag_query.py "问题" --hybrid`

---

## 6. RAG 与 memory/skill 的边界（什么进 RAG 什么不进）

| 内容类型 | 例 | 去向 | 原因 |
|---|---|---|---|
| 禁令/铁则（必须遵守） | phase1/2 禁入库、禁 git 写、Excel 唯一位置 | **MEMORY+SKILL，绝不 RAG** | RAG 按相似度不按权威/时效，相似旧版可能压过最新版 |
| 用户偏好 | 展示方式、学习方式 | USER（注入） | 必须在场，检索反而漏 |
| 当前流程/命令 | 命令速查、工具优先 | SKILL（注入） | 高频操作入口 |
| 机制知识（how X works） | DDA 公式、DB 结构、判定分档、探针反推 | **references + RAG** | 量大、定义性、检索命中率高 |
| 定稿数值/格式 | 目标胜率、Excel 格式、payload 结构 | references（RAG 可检索其定义） | 精确性要求，靠 INDEX 定位 |
| 时效性决策（未定稿） | "待用户决策是否 bot400 重写 DB" | references + INDEX，不进 RAG | 变了就要换语料，成本高 |
| 事故复盘叙事 | L57 穷尽过程、某 bug 排查链 | references（短期）→ archive → session_search | 只调试时用，检索会干扰知识纯度 |
| 会话历史 | 任何旧对话 | session_search | 天然存在 |

一句话：**RAG 回答"是什么/怎么工作"，memory 回答"我绝不能做什么/用户要什么"，skill 回答"现在这个任务怎么做"，references 回答"细节在哪看"，session_search 回答"以前发生过什么"。**

---

## 7. 实施顺序（P0→P1→P2，每步可独立交付）

- **P0（今天，纯文档，无风险）**：
  1. MEMORY.md 按 §3 清到 ≤15KB（先备份 .bak）
  2. USER.md 按 §4 去重到 ≤8KB
  3. SKILL.md 按 §2 瘦身到 ~30KB（坑表拆 4 文件 + 判定速查表 + References 一行指针）
  4. 清理项目内过期 `hermes/memories/` 旧快照（7-31 勿用，标记或删除，防误读）
- **P1**：INDEX.md 加 `RAG` 列 + 执行 2 周归档（07-31 的 12 个文件按规则归档）；SKILL 使用规则加"新知识先判层"
- **P2**：RAG 扩语料（§5 全套：knowledge 子集 + Bot/Tools + golden QA 扩到 ~70 + 重建 + 评估），验证 recall@1 不降反升

**验证方法**：每步后跑一次真实任务（如"跑一遍 L151 判定"），确认瘦身后的 SKILL/MEMORY 仍能完成；RAG 扩语料后跑 `rag.eval` 对比召回率。
