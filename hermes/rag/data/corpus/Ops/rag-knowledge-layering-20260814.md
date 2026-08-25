# RAG vs skill/memory 知识分层（2026-08-14 方案）

> 触发：用户问"我们不是有 rag 吗，有需要放到里面的吗？"→ 产出 `hermes/rag-知识分层与扩语料方案-20260814.md`（完整方案 8 节）。
> 扩语料/整理 knowledge 时先读本文件，再动手。

## 四判据：进 RAG（同时满足）
1. **体量大**（>100KB 值得考虑）
2. **按需查询**（特定症状/场景才需要，不是每次动手都碰）
3. **语义查询**（自然语言能定位，而非精确命令/路径）
4. **不太常触发**（低频；高频的放这反而每轮多一次工具调用）

## 四判据：留 skill/memory（任一满足）
1. **必须每次都记得**（遗忘=事故：安全闸门/用户禁令/不可逆操作）
2. **高频触发**（每次动手要过一遍的工具清单/命令映射）
3. **时效精确**（当前标准/目标值/参数——过期就是错的）
4. **行动指令**（怎么写 asset/调工具，命令必须精确且当前，历史版本害人）

## RAG 本质局限（决定边界）
- **RAG 是主动查询架构**：agent 不调 `rag_query.py`，语料=不存在。Hermes 当前无自动 RAG 钩子。
- 因此**"必须记得"的绝不能放 RAG**（=降级成"运气好才查到"）。skill INDEX.md 已承认失败模式："有记录但没被触发"（reference 太多 → 检索失效）。
- RAG 返回的是**证据/参考，不是权威**：语料含过期内容（判定标准 15→10pp 旧版），命中旧 chunk 会误导。当前标准真源=MEMORY/rules.json。

## BlastGame 现状判定（实测 2026-08-14）
- skill references：**119 文件 626KB**（SKILL.md 本身 166KB）。按文件名日期模式分类：
  - **96 个带日期的事故复盘/案例 = 512KB → 进 RAG**（bot400 一致性、白/红关根因、L57 穷尽案例、fixes 批次、大审计、multi-tier 设计史——均已被新机制取代）
  - **23 个无日期现行规则 = 114KB → 留 skill**（judgment-rules、probe-efficiency-standards、pool-data-integrity、tool-first-rule、auto-loop、warden-gate、dda-runtime、INDEX 路由表）
- `tool-fixes.md`（22.7KB/33 条）**拆开**：案例部分进 RAG 语料，现行用法留 skill。
- MEMORY.md 33.7KB/147 条：**同一主题跨日期重复 3-5 次**（探针铁则 5+、局数标准 4、判定标准 3、bot400 一致性 3）→ 压缩合并到 ~70 条/~20KB；叙事细节挪 Ops 语料；旧版本归档**不删**（压缩后 MEMORY=现行真源）。

## 落地路径（改造成本低，现有 build_index 已支持 CORPUS_SUBDIRS）
1. 建 `<BLASTGAME_REPO>/Doc\Ops\` **快照语料**：从 skill references 拷贝 96 个日期文件，头部加一行 `> ⚠️ 已被 <新标准> 取代（日期），仅供历史参考`；**不直接索引 skill 目录**（防漂移/INDEX 噪声/个人内容）。
2. `build_index.py` metadata 加 `domain` 字段（~10 行）；`rag_query.py` 可选 `--domain` 过滤。
3. 重建：`RAG_CORPUS_SUBDIRS="MainGame,Bot,Tools,Ops" python -m rag.build_index`（928→~1450 chunk）。
4. 新建 `rag/data/golden_qa_ops.json`（20-30 条，expected_source 指向 Ops/ 文件名）+ 双域评估；**design 回归掉 >3pp → 切双索引**（ops 复盘文可试更大 chunk）。
5. **最关键=触发路由**：`.hermes.md`（每次自动加载）+ MEMORY 一行铁则——症状类问题（白档/红关/胜率不一致/变慢/卡死）第一反应 `rag_query.py "症状" --hybrid` 查 Ops 历史，再动手。
6. 一周复盘触发率；若 <50% 症状场景先查了 RAG → 最高频 10 个案例摘要写回 SKILL.md，RAG 只留长尾。

## 不能放 RAG（边界清单）
安全闸门（git 全禁/入库必须确认/禁碰 Unity 核心文件）；工具命令映射（tools/README）；当前标准/目标值（rules.json 真源）；数据可靠性硬约束（phase1/2 禁直接入库、filter_verified、时间防线、dedup 按配置不按档位、reimport 后回读 DB）；用户工作流偏好（展示→确认→执行、用户裁定权）；有副作用/时效敏感的精确指令（write_ddc/gen_payload/reimport 用法，08-14 事故即手写 payload 误传 50 关）；个人/隐私内容（个人叙事不入语料）。

## 清理（与 RAG 无关的杂物）
hermes 根 30 个 `手动挑配置记录_before_*.bak`（1098KB）归档；references 超 2 周且被覆盖的移 `_archive/`（INDEX.md 规则 #3）；`hermes/memories/` 7-31 旧快照删除。
