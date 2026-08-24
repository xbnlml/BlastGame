# Agent 责任化改造——可执行落地设计（落地设计派终稿）

> 日期：2026-08-19 · 状态：**落地设计定稿**（承接 `agent-ownership-rework-20260819.md` 草案 v1）
> 立场：落地设计派。把草案补全到函数/文件/Schema 级别：监督点→问题库→memory 消费者→迭代闭环→继承框架→成本预算。
> 现状锚点（已查证）：auto_loop.py(1057 行) 5 阶段 6 轮状态机；curator 是 memory 唯一写方、零消费者；auto_loop L1046 以 `capture_output=True` 调 curator 吞输出；rules.json 是规则唯一真源；warden.py 中 W01/W03/W09 检查函数已定义但 run_warden 未 dispatch（死代码）；probe-design-llm-final 的 S1（llm_client/advisor/packager）已落地，S2 llm_probe_pipeline.py 未建。

---

## 0. 架构总览

```
 ┌──────────────────────────  auto_loop.py（6 轮状态机，主流程不动）──────────────────────────┐
 │                                                                                            │
 │ Phase1 phase_analyze(L767) → Phase2 phase_apply_probes(L817) → Preflight+Warden(L850-891)   │
 │ → Phase3 phase_submit_batch(L901) → Phase4 phase_refresh_pools(L918) → Phase5 phase_review  │
 │   (L922) → round_report(L990) → checkpoint(L999) → curator(L1043-1048)                      │
 └──────────────┬──────────────────────────────┬──────────────────────────────┬───────────────┘
                │ 监督钩子(确定性,每环节边界,零LLM)  │ 评价钩子(round_report,数据)      │ 复盘钩子(批次末)
                ▼                               ▼                              ▼
      tools/agents_supervision.py      tools/probe_hitrate.py          tools/problem_analyzer.py
      (每 agent 的检查器注册表)          (探针三维评估+教训库)          (聚合→喂LLM)
                │                               │                              │
                ▼                               ▼                              ▼
      project-state/problem_db/events.jsonl  probe_blacklist.json(l教训库)   tools/iteration_reviewer.py
      (结构化问题库,只追加)                                                    (LLM,批次末1次调用)
                                                                                │ 提案
                                                                                ▼
                                                          problem_db/proposals/<agent>_<ts>.json
                                                                                │ 人确认(主 agent 转述用户)
                                                                                ▼
                                                          tools/apply_proposal.py (白名单写+rules.json版本bump)
                                                                                │ 下一轮验证
                                                                                ▼
                                              监督器检查"新标准被遵守" → verified | rolled_back

 记忆消费者链路：llm_probe_pipeline 读 planner memory(教训库) | judge_level 校验 rules.json 版本
                | warden_framework 审计 memory 声明 vs rules.json 注册 | iteration_reviewer 读全部
```

三层责任：**规则驱动安全（Warden）· AI 负责判断（Planner LLM 探针 + 批次末复盘）· 数据负责验证（round_report/probe_hitrate）· 人负责裁定（提案确认）**。

---

## 1. 四 Agent 监督点（指到函数/行，监督什么输入输出、异常怎么捕获）

### 1.0 基础设施：`hermes/tools/agents_supervision.py`（新增，纯确定性）

- `AGENT_STAGES` 注册表：`{'planner': 'phase1', 'judge': 'phase5', 'warden': 'phase2/3boundary', 'curator': 'post'}`
- `supervisor.record(event)` → 校验 schema → 追加 `project-state/problem_db/events.jsonl`（见 §2）
- `load_agent_standards(agent, lv=None)` → 返回该 agent 的标准层文件清单 + 版本号（被 auto_loop 各阶段加载，专治"memory 无消费者"）
- `check_standard_consumed(agent)` → 日志断言该 agent memory 本轮被加载过（供迭代闭环验证用）
- **异常捕获通用约定**：所有监督钩子包 try/except，捕获到异常一律 `record({'severity':'block','kind':'supervisor_self_failed','observed':str(e)})` 并继续主流程（fail-open：监督器自身故障绝不能停主流程，但必须留痕）。

### 1.1 Planner —— 负责"调优方向"（Phase 1 + 探针写盘）

| # | 监督规则 | 钩子位置（文件:行） | 监督的输入/输出 | 异常捕获 |
|---|---|---|---|---|
| P01 | probe_present | `auto_loop.py:767` `probes = phase_analyze(...)` 返回后 | 输入：planner.py stdout；期望：每关 probes ≥5 槽 + combo + judge 字段齐全 | planner 返回 None / extract_json 失败 / `r['error']` 非空 → `record(kind='probe_design_failed', severity=block)`；同时驱动 fallback L776 |
| P02 | probe_novel | `auto_loop.py:335-337` probe_configs.json 写盘前 | 输入：本轮 5 槽四元组 vs `probe_blacklist.json`（教训库已升级为 L1 邻近域匹配）vs 上轮 used_keys；期望：零碰撞 | 碰撞 → `record(kind='probe_collision')`，W09/W10 闸门兜底拦截 |
| P03 | probe_direction | `warden.py:244` `check_probe_direction`（W10）结果 | 输入：W10 输出的 issues；期望：无 warn 级"方向错误" | W10 自身异常（fail-closed 已在 L260-264 处理）→ 追加 record 关联 |
| P04 | llm_usable | `tools/llm_probe_pipeline.py::design_probes_llm()`（S2 新建） | 输入：`llm_client.available()` + advisor.mode；输出：LLM 方案 or None | None（fail-open）→ 记 `kind='llm_fallback_script'`，本轮走 design_probes 兜底——从这里开始 planner 的 AI 点有真实记账 |
| P05 | hitrate_tracked | `tools/probe_hitrate.py::record_round(round_report)` | 输入：`auto_loop_round_report.json` 的 probes+batch_wrs；输出：三维评估（新边界信息/方向正确率/收敛贡献）+ borrowed 血缘剔除 | round_report 缺字段 → 跳过该关不记账，`severity=warn` |

**Planner 的 AI 落地**：`llm_probe_designer`（=探针 LLM 化 S2 的 `llm_probe_pipeline.py`）是 planner 的执行器；`probe_design_v1.txt` 第 4 段教训库 = planner memory 的直接消费者（见 §4.1）。

### 1.2 Judge —— 负责"判定权威"（Phase 5）

| # | 监督规则 | 钩子位置（文件:行） | 监督的输入/输出 | 异常捕获 |
|---|---|---|---|---|
| J01 | verdict_emitted | `auto_loop.py:922` `review_results = phase_review(...)` 后 | 输入：每关 {result, reasons, round, action}；期望：result ∈ {合格,接近,不合格,无数据} | results 缺关 → `record(kind='judge_missing_level', severity=warn)` |
| J02 | boundary_capture | `judge_level.py:78` `check_judgment()` 返回 reasons 后；钩子写 `judge_level_supervised()` 包装（改调用点 `auto_loop.py:557` 与 `planner.py:55`） | 输入：combo WR、diff、targets、reasons；确定性边界判定：`gap∈[ok_lo−tolerance−3, ok_lo+tolerance]` 或 `dev∈(td_ok, td_near+tolerance]` → 记边界案例（含精确数值，L152/L54 教训式） | 无异常路径（纯计算） |
| J03 | user_ruling_feedback | `tools/judge_level.py` 新增 `record_ruling(lv, judge_result, user_ruling, comment)`；回调入口 `tools/apply_proposal.py` | 输入：auto_loop 判定的 result vs 用户最终裁定（入库/改关/维持）；期望：一致 | 用户裁定未落 decision 记录 → `severity=warn`（防"用户裁了没回流"） |
| J04 | rules_version_ok | `judge_level.py:20` `_load_rules()` 内增加版本校验 | 输入：rules.json `_meta.version` vs `agents/judge/memory.md` front-matter 声明的 version；期望：一致 | 不一致 → `record(kind='rules_memory_drift', severity=warn)`——这是"memory 与真源漂移"的哨兵 |

**约束（批判评审已确认）**：Judge 的 LLM 点 = 0 次判定调用。判定只吃 verified 数据 + rules.json 阈值；边界案例走"用户裁定→变规则"确定性闭环，LLM 不猜判定。

### 1.3 Warden —— 负责"安全闸门"（Phase 2/3 边界）

| # | 监督规则 | 钩子位置（文件:行） | 监督的输入/输出 | 异常捕获 |
|---|---|---|---|---|
| W01r | gate_fired | `auto_loop.py:885-891` warden 调用返回后 | 输入：exit code + stdout（BLOCKED/WARNINGS/PASSED）；期望：记录每条 failures+warnings 到问题库 | warden 自身 crash（非零退出无输出）→ `record(kind='warden_self_failed', severity=block)`。注：现 run_warden L388-389 的 except 已在内部把检查异常转 failures，钩子只需收最终结果 |
| W02r | gate_coverage | `warden.py:341` `run_warden()` 重构后 = `warden_framework.run()` 遍历注册表 | 输入：rules.json pre_batch 的 id 列表 vs 注册表 keys；期望：双向一致 | 发现"已定义未注册"（现 W01/W03/W09 死代码状态）→ `record(kind='warden_rule_not_registered', severity=warn)` 并自动纳入注册表（见 §5） |
| W03r | miss_detected | `tools/agents_supervision.py::post_batch_warden_miss()`（批次末,读 round_report） | 输入：成功提交但结果异常的关（CSV 缺档、dedup 吃槽、WR 越界）+ 该轮 Warden 全部通过；期望：反推"若加了某规则可否拦住" → 可拦则 `record(kind='warden_miss', severity=warn)` 且该记录自动成为迭代提案候选 | round_report 不可读 → 跳过 |

### 1.4 Curator —— 负责"经验沉淀"（收尾）

| # | 监督规则 | 钩子位置（文件:行） | 监督的输入/输出 | 异常捕获 |
|---|---|---|---|---|
| C01 | output_harvested | `auto_loop.py:1046-1048` 改为捕获 stdout：`subprocess.run(..., capture_output=True)` → `json.loads(stdout)` 并落 `project-state/curator_report_<log>.json` | 输入：curator 结构化输出（整改后的 supervise 结果 + 统计）；期望：supervisor 报告结构完整 | 解析失败 → 记 warn 并打印原样输出（不再静默吞） |
| C02 | lossless_patterns | `curator.py:37` `detect_patterns()` 重构为读 `auto_loop_round_report.json` + problem_db 聚合（废除正则空洞计数） | 输入：round_report 每关 probes/batch_wrs/judge；输出：模式聚合（gap不足/方向错/设计失败/资产写入失败，均带关卡号+数值） | round_report 缺 → 回退读日志但标记 `severity=warn`（有损路径禁入 memory） |
| C03 | supervision_honest | `curator.py:88` `supervise()` 重写：阶段时序改为读结构化阶段时间戳序列（废除 L118-123 坏正则 `['1','1','1']` 误报半年问题） | 输入：auto_log 的 `[Phase n/5]` 行序列 + 时间戳；期望：1→2→3→4→5 顺序 | 无法解析 → 记一条 `curator_supervise_failed`，不写误报进 warden memory |
| C04 | memory_consumer_check | `curator.py:68` `AUTO_SECTIONS` 表维护；批次末校验各 agent memory front-matter 的 `consumers:` 声明 | 输入：各 memory 文件 front-matter；期望：每个 memory 的消费者字段非空且加载点存在 | 发现"无人读的 memory 段"→ `record(kind='memory_no_consumer', severity=warn)`——这条规则让"记忆无消费者"永久可检测 |

**Curator 的 AI 点**：不是每轮；批次末由 iteration_reviewer（§4 第 3 步）读 curator 的聚合输出做"模式解读+归因",归因到负责的 agent。Curator 自己保持纯确定性。

---

## 2. 问题库 Schema（结构化记录，只追加，可回放）

### 2.1 存储布局

```
hermes/project-state/problem_db/
  events.jsonl                      # 监督器写（每行一个事件）
  aggregate/<batch>.json            # 批次末聚合器写（读side）
  proposals/<agent>_<ts>.json       # 迭代提案（LLM 写，status=proposed）
  applied/<agent>_<ts>.json         # 已确认落地（apply_proposal 移动）
  decisions.jsonl                   # 人确认记录（approved/rejected/modified + 用户评语）
index.json                          # owner×kind×status 轻索引（聚合器维护，可重建）
```

### 2.2 Event 记录 Schema（events.jsonl 每行）

```json
{
  "id": "EVT-20260819-000123",
  "ts": "2026-08-19T09:41:22+08:00",
  "batch": "20260819_091500",
  "round": 3,
  "owner": "planner",
  "stage": "phase1",
  "supervisor": "P01_probe_present",
  "severity": "block|warn|info|miss",
  "level": "136",
  "kind": "probe_design_failed | probe_collision | warden_block | warden_miss | boundary_case | judge_missing_level | rules_memory_drift | memory_no_consumer | llm_fallback_script | supervisor_self_failed",  // kind 注册在 AGENT_STAGES,不在代码中散落
  "input": {"levels": ["136"], "probes_requested": 5},
  "observed": {"result": null, "stderr_tail": "planner exit=1"},
  "expected": "probes>=5 per level",
  "context": {"log_path": "auto-log/20260819_091500.log", "log_line": 123, "probe_file_hash": "sha256:ab12..."},
  "resolution": {
    "first_seen": "2026-08-19T09:41:22+08:00",
    "occurrences": 1,
    "linked_proposal": null,
    "status": "open"   // open|proposed|approved|applied|verified|archived
  }
}
```

约束：`input/observed` 只存关键字段（≤1KB/事件），大对象（stdout 全文/CSV）只留 `context` 溯源指针；`kind` 必须存在于 `AGENT_STAGES.kinds` 否则 `record()` 拒绝（防脏数据）。

### 2.3 生命周期

- **写**：监督器（确定性）经 `supervisor.record()`；`apply_proposal.py` 落地时写一条 `kind=standard_applied` 事件（闭环证据链）。
- **读**：① `problem_analyzer.py --batch <log>` 批次末聚合（按 owner×kind×level 计数 + 数值抽样）→ aggregate；② `iteration_reviewer.py`（LLM）读 aggregate + round_report；③ 主 agent 用 `problem_db.py query --owner planner --status open` 转述给用户；④ 迭代闭环验证阶段读 status 流转。
- **只追加**：events/decisions 永不 rewrite；proposals 靠移动文件改状态（proposed→applied/archived），保留原始提案。

---

## 3. Memory 消费者机制（每一条 memory 都有机器消费者）

### 3.1 Memory 双层结构（全部文件迁移，README 更新）

| 层 | 文件 | 读者 | 写入者 |
|---|---|---|---|
| 叙事层 | `agents/<agent>/memory.md` | 主 agent（转述时）、人 | curator + 迭代闭环（结构化追加） |
| 标准层（机器可读） | `agents/<agent>/rules.md`（front-matter: `version`, `updated`, `consumers: [加载点列表]`, `status: active`) | **auto_loop/tools 加载点** | apply_proposal.py（唯一写入入口） |

现有 `memory.md` 迁移：内容按 front-matter 化 + 历史附录保留（只读不删）；`curator.py` 的 `update_memory()` 改为写 front-matter 结构化块（时间戳/来源事件 id/内容），禁止再自由文本追加。

### 3.2 消费者加载点（auto_loop/tools 具体位置）

1. **Planner memory（教训库）消费者 = LLM 探针设计器**：`llm_probe_pipeline.py::design_probes_llm(lv)` 加载 `probe_design_v1.txt` 模板第 4 段时，读 `probe_blacklist.json`（升级版教训库：`{reason, direction, 实测WR, 轮次, L1邻近域}`）+ 最近的 3 条 planner 失败探针记录，注入 prompt。**这就是规划草案里"只有 curator 写、无人读"的 planner memory 的第一个真实消费者。**
2. **Judge 标准消费者 = rules.json 版本哨兵**：`judge_level.py:20 _load_rules()` 校验 `agents/judge/rules.md` front-matter 的 version 与 rules.json `_meta.version` 一致（不一致 → J04 事件）。rules.json 仍是**唯一判定真源**；judge rules.md 只声明"我依据的版本"，防止人改了 rules.json 而 memory 忘更新。
3. **Warden 标准消费者 = warden_framework 注册审计**：`warden_framework.py` 加载 `agents/warden/rules.md` 的"已注册规则清单"，与 rules.json pre_batch 比对（W02r）。warden memory 里记录的"新增违规模式"必须能映射到一条已注册检查，否则记 `warden_rule_not_registered`。
4. **Curator 消费者 = iteration_reviewer**：批次末聚合时读全部 4 个 agents/*/rules.md 的 front-matter（版本+变更摘要），让 LLM 复盘"本轮改动是否有据可依"。
5. **加载日志把关**：`load_agent_standards()` 每次加载打印 `[MEMORY] loaded <path> v<n> consumers=<list>`；auto_loop 日志出现该行是 C04 监督器的通过判据。**验证消费者机制生效 = 日志里有加载行 + 修改标准后下一轮该加载点输出行为变化**（例如教训库注入后 LLM 拒绝同域配置）。

### 3.3 防"写给自己看"终检

`tools/agents_supervision.py::audit_memory_consumers()`（可 cron/手动跑）：扫所有 memory/rules.md 的 consumers 声明，逐一确认加载点存在（grep 定位），找不到 → `C04 memory_no_consumer` 事件。该审计本身就是"记忆无消费者"问题的永久监督器。

---

## 4. 迭代闭环（LLM 分析→提案→人确认→落地→验证）

### 4.1 触发频率

按 llm_advisor `reflect_every_n_rounds`（现 0=关）控制：正常轮每轮 0 次 LLM；批次末 1 次综合复盘；触发式卡壳参谋（某关连续 ≥2 轮黑名单新增且 WR 未动）。**不逐轮反思**（用户明确要求）。

### 4.2 六步闭环

```
第N轮运行
 ① 监督（确定性，每环节边界，§1）→ events.jsonl
 ② 聚合（批次末）tools/problem_analyzer.py --batch <log>
    → problem_db/aggregate/<batch>.json（按 owner×kind×level 计数+数值抽样+关联 round_report 摘要）
 ③ 分析（LLM，批次末 1 次）tools/iteration_reviewer.py --aggregate <file>
    prompt = 聚合结果 + round_report 缩略(分关≤5K token) + 各 agent rules.md front-matter + 用户决策史(decisions.jsonl 摘要)
    输出：为每个值得处理的 problem 给出根因/归属 agent/标准改进建议（json_mode）
 ④ 提案 → problem_db/proposals/<agent>_<ts>.json（status=proposed；schema 见 4.3）
 ⑤ 人确认：主 agent 读提案转述用户 → 用户 approved/rejected/modified
    → decisions.jsonl 追加一条 {proposal_id, decision, comment}
 ⑥ 落地 tools/apply_proposal.py --id PROP-xxx
    - 只允许写白名单：project-state/rules.json（bump _meta.version）、agents/*/rules.md、agents/*/memory.md、
      probe_blacklist.json、probe_design_v1.txt
    - 写前备份规则文件到 project-state/_backup/<ts>/；写后更新 problem_db 事件 status=applied
 ⑦ 验证（下一轮）：该 agent 监督器检查新标准被遵守（如新阈值生效/新检查被 dispatch/教训库拦截到同域配置）
    → 通过: status=verified（记 verification 证据）；失败: 从 backup 回滚 → status=rolled_back + 告警
```

**安全阀**：LLM 永不直接写规则文件（apply_proposal 是唯一入口）；应用前 must 通过 `apply_proposal.py --dry-run` 的 schema 校验；rules.json 任何变更先 `diff` 展示给用户再写。

### 4.3 提案 Schema

```json
{
  "id": "PROP-planner-20260819-001",
  "ts": "2026-08-19T11:20:00+08:00",
  "batch": "20260819_091500",
  "trigger": {"aggregate": "20260819_091500.json", "events": ["EVT-..", "EVT-.."], "reason": "L52 缺口段连续3轮未收敛(22pp/21pp/22pp)，方向命题CONFLICT"},
  "owner": "planner",
  "change": {
    "target": "probe_blacklist.json",          // 或 rules.json#judge_rules... / agents/*/rules.md / probe_design_v1.txt
    "op": "update|append|rotate",
    "old": {"key": "(31,5,'10,1,1,1,1',0.5)", "domain": "L1≤2"},
    "new": {"key": "(31,5,'10,1,1,1,1',0.5)", "domain": "L1≤3", "direction": "sd↑→WR↓", "wr": 12.3},
    "rationale": "LLM 分析：三轮回溯验证方向命题失效，该域应扩大拒绝半径",
    "evidence": ["round_report L52 r3-5", "probe_hitrate.json L52"]
  },
  "verification": {"check": "P02_probe_novel", "expect": "下一轮同域配置被拦截或方向翻转"},
  "status": "proposed",
  "decision": null
}
```

### 4.4 生效验证的机械性

验证不靠 LLM 自评：第 ⑦ 步用**监督器运行两次对比**——apply 前后各跑一次该监督规则（如 `P02_probe_novel` 对历史关卡回放），断言"新增拦截事件数>0 或拦截规则命中率变化符合预期"。回放输入 = 历史 probe_configs + round_report（机械区分"LLM 选错 vs 数据不支持 vs 校验拒错"，与探针 LLM 化 §10 回放审计同一方法）。

---

## 5. 监督继承框架（新检查怎么加而不破坏 W01-W10）

### 5.1 现状问题（审计已确认）

- `warden.py` 定义了 `check_sd_span(W01)`、`check_ratios_diversity(W03)`、`check_probe_quality(W09)`，但 `run_warden()` 的 if/elif dispatch（L348-387）**没有它们**，rules.json pre_batch 也只注册了 W00/W02/W04/W05/W06/W07/W08/W10 → 三处不同步，死代码半年无人发现。
- 新增检查 = 改 代码函数 + rules.json + dispatch 三处，必漏。

### 5.2 声明式注册框架 `tools/warden_framework.py`（新增）

```python
WARDEN_CHECKS = {}          # id -> WardenCheck

class WardenCheck:          # 基类，新检查继承即可获得：结果格式化/severity/问题库记录/单测夹具
    id: str; name: str; severity: str = 'block'
    inputs: tuple = ('levels',)     # 声明需要的上下文键（tiers_map/probe_file/lesson_db/...）
    def run(self, ctx) -> tuple[bool, str]:  # 返回 (ok, message)，子类实现
    def record(self, event): ...     # 框架自动调用 supervisor.record()

def warden_check(id, name, severity='block', inputs=('levels',)):
    def deco(fn):
        WARDEN_CHECKS[id] = WardenCheck(id, name, severity, inputs, fn)
        return fn
    return deco

# 迁移示例：W10 从手写 if/elif 改为装饰器
@warden_check('W10', 'probe_direction', severity='warn', inputs=('levels', 'tiers_map'))
def _w10(ctx): return check_probe_direction(ctx['tiers_map'])

def run(ctx):                 # 取代 run_warden() 的 if/elif 链
    for cid in rules['warden_checks']['pre_batch']:     # rules.json 决定启用与 severity
        check = WARDEN_CHECKS.get(cid)
        if check is None:
            record(warden_rule_not_registered, cid); continue
        inject = {k: ctx.get(k) for k in check.inputs if k in ctx}
        ok, msg = check.run(inject)                      # 统一 try/except → failures/warnings
        check.record(...)                                # 问题库
        return passed, failures + warnings
```

### 5.3 迁移与契约测试（不破坏 W01-W10）

1. `run()` 新实现逐条调用迁移后的 W00..W10，**输入输出与旧 `run_warden` 完全一致**。
2. `scripts/smoke_test.py` 新增：`test_warden_registry`（rules.json 每个 pre_batch id ∈ WARDEN_CHECKS，反向也成立）；`test_warden_behavior_unchanged`（同一探针输入，新旧实现输出相同 → 先跑旧实现存 golden，再切新实现比对）；`test_warden_negative`（坏探针必 BLOCK，延续现有测试）。
3. **新增检查路径**：① 写一个 `@warden_check` 函数（继承即插即用）② 可选在 rules.json 加 id（不加速默认启用）③ 加负例单测。**无需改 dispatch**。提交门槛 = 三个契约测试全绿 + 问题库有该检查的 rule_not_registered 清空。

### 5.4 产出物

`warden.py` 保留 CLI 与 `run_warden()` 名字（auto_loop L882 调用不动），内部改为代理 `warden_framework.run()`；`rules.json` `_meta.version` 升 1.1.0 记录框架迁移。

---

## 6. 与探针 LLM 化的衔接（合并方案）

- **现状**：probe-design-llm-final 的候选选择器已接入 `auto_loop.phase_analyze`；模型/provider 跟随 Hermes 当前配置，失败回退脚本。
- **合并**：Planner agent 的 AI 化 = S2-S4 的上层编排；本方案的监督/迭代闭环 = 这些 LLM 产出的评价与反哺层。两者是同一件事的两面，统一在 `roles.json` 的 planner 名下。
- 合并点明细：
  1. `llm_probe_pipeline.py::design_probes_llm(lv, round_num)` 调用 `llm_client.ask(..., agent='probe')`，只返回 candidate_id 选择；usage 和 `ai_probe_metrics.jsonl` 记录设计与实际 WR。
  2. round_report 读取同一 receipt 的 batch_wrs，记录新候选、重复率、Judge 结果和 Unity 局数；不额外跑控制批次。
  3. `llm_advisor.json` 的 `mode=llm/script` 驱动正式选择或脚本回退，不启动 shadow/双通道/Canary。
  4. 教训库升级（邻近域 L1≤ε 泛化）由 4.4 的验证闭环自动增补——LLM 方案被 W 闸门拦下 → W03r miss/block 事件 → 复盘 → 提案扩教训库。**规则闸门和教训库互相喂养，闭环自洽。**

---

## 7. 成本预算（每批/每月，实测口径深挖）

基准：4 关/批次 × 6 轮 = 24 关轮；配额 opencode-go 08-21 重置，advisor `daily_call_limit=200`（6000 次/月上限）。

### 7.1 每批次

| 用途 | 归属 | 调用次数 | token（输入+输出） |
|---|---|---|---|
| 探针设计（S2 主导后） | planner/P04 | ≤24 次（每关轮 1）+ 打回 ≤3 次/关轮 ≈ 平均 1.4 → **34 次** | 每关轮 ~2.5K in + 0.4K out ≈ 3K → **~100K** |
| 批次末综合复盘 | 暂不做 | **0 次** | 由正式 round_report 记录结果 |
| **合计** | | **≤34 次** | 每关每轮一次，失败最多 3 次校验重试 |

### 7.2 每月

- 调用量按实际关卡数×轮数计，受 `daily_call_limit` 限制；模型失败直接脚本兜底。
- 最坏打回链：每关每轮最多 3 次校验重试，不增加 Unity 批跑。

### 7.3 零成本项

- 全部监督器（§1 的 P/J/W/C 规则）：**0 次 LLM**，纯确定性脚本 + 问题库 I/O（微秒级，无网络）。
- 聚合器/回放审计/契约测试：0 次 LLM。
- 反思频率：`reflect_every_n_rounds` 默认 1（每批次末 1 次），设 2 则可再砍半（约 560 次/月）；删除**不逐轮回顾**（用户裁定）。

### 7.4 记账与熔断（复用 llm_client）

`llm_usage.jsonl` 每行：`{ts, agent, task, model, prompt_tokens, completion_tokens, latency_s, status}`；`llm_advisor.json` `daily_call_limit` 是唯一熔断闸；新增 `weekly_budget_guard.py`（可选）统计 7 日滚动用量，超预算告警。所有数字可随时 `python tools/llm_client.py --usage` 复核，不用猜。

---

## 8. 落地顺序（映射原草案 S1-S5，附验证）

| 步 | 内容 | 关键文件 | 验证 | 回退 |
|---|---|---|---|---|
| S1 | 问题库 + 监督基础设施 | `agents_supervision.py`、`problem_db/` | 单测：record/query/聚合 | 不写 events |
| S2 | 四 agent 监督钩子植入 auto_loop 各阶段 | `auto_loop.py`（钩子 6 处）、`curator.py` 重构 | 跑 1 轮，7 类事件落库 | 钩子可不生效（读开关 `supervision.enabled`） |
| S3 | memory 双层 + 消费者加载点 | `agents/*/rules.md`、`load_agent_standards` | 日志出现 `[MEMORY] loaded` 行 | 不加载 |
| S4 | 迭代闭环 | `problem_analyzer.py`、`iteration_reviewer.py`、`apply_proposal.py` | 提案→确认→落地→验证全链 dry-run | 关 `reflect_every_n_rounds` |
| S5 | warden 框架迁移 + 契约测试 | `warden_framework.py`、`smoke_test.py` | golden 比对 + 注册表双向一致 | 切回旧 run_warden |
| S6 | 与现有 auto_loop 合并 | `llm_probe_pipeline.py`、`auto_loop.py`、`ai_probe_metrics.jsonl` | fake Hermes 契约 + 正式 receipt WR 回流 | mode=script |

**运行约束**：模型/provider 跟随 Hermes 当前配置，reasoning=max；不启动额外 shadow/canary 批次。

---

*本文档由「落地设计派」按其立场产出，与草案 v1 冲突处以本文件为准。所有行号锚定 2026-08-19 代码快照（auto_loop.py v1057 行版）。*