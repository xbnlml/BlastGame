# BlastGame「让每个 agent 真正参与思考」改造方案

> **历史方案。** 后续职责已收敛到 Planner 的受限选择、确定性 Warden/Judge 和用户裁定；本文未落地项不能视为现行能力。当前实现以代码、角色 manifest 和 `probe-design-llm-final-20260819.md` 为准。

> 日期：2026-08-19 · 状态：方案（待用户确认后分步落地）
> 目标：在不推翻"可靠优先"基因的前提下，让 Planner/探针/Judge/Warden/Curator 每个 agent 都有真实的思考痕迹。
> 总纲：**规则驱动（主判） + LLM 参谋（建议旁路） + 数据回测（验证） + 人（最终裁定）**。LLM 永远不当主判。

---

## 0. 一句话方案

所有 `tools/*.py` 保持 100% 确定性执行路径不动；新增一个**参谋层（Advisor Layer）**——LLM 只在你指定的几个"思考点"上读结构化摘要、产出建议/反思、落盘可审计文件；规则继续兜底、结果不变、人继续裁决。改造前后主流程输出**逐字节一致**，差异只在多出来的 `project-state/advisor/` 文件和 memory 反思区。

## 0.1 前提已验证

- 本机已有可用的 OpenAI 兼容 LLM 端点：`https://ark.cn-beijing.volces.com/api/coding/v3`，模型 `deepseek-v4-flash-ga-260731`，key 在 `HERMES_CUSTOM_CUSTOM_API_KEY`。**已实测直接调用成功**（一次纯文本 ~113 token）。脚本无需引入 Hermes 全家桶，直接用 urllib 或 requests 即可，零新增依赖。
- 这是成本最低、最可控的调用方式（不启动完整 agent，只发一次 chat/completions）。

---

## 1. 基础设施：`tools/llm_client.py` + 开关 + 记账（一切改造的前提）

约 60 行的极简封装，是唯一允许发 LLM 调用的入口。

```python
# tools/llm_client.py（示意）
def ask(system: str, user: str, *, max_tokens=300, json_mode=True) -> dict | None:
    """调用 LLM。任何失败（超时/无key/解析失败）→ 返回 None，绝不抛异常。"""
    # 读 project-state/llm_advisor.json 的 enabled/model/max_tokens
    # 读 config.yaml 的 base_url/key_env（或直接读 env HERMES_CUSTOM_CUSTOM_API_KEY）
    # 超时 30s、重试 1 次；成功则把 usage 记入 project-state/llm_usage.jsonl
```

配套三件套（Step 1 一起交付）：

| 文件 | 作用 |
|---|---|
| `project-state/llm_advisor.json` | **总开关 + 限额**：`{enabled, model, max_calls_per_round, reflect_every_n_rounds, judge: {...}}`。改这里即可一键关停/调限额，零代码回退 |
| `project-state/llm_usage.jsonl` | token 记账：每次调用追加 `{ts, agent, level, prompt_tokens, completion_tokens, latency}`——成本可查、可设月上限告警 |
| `project-state/advisor/` | 所有 LLM 建议/反思落盘目录，`<agent>_<lv>_<ts>.json`，只追加不覆盖 |

**铁律：参谋层 fail-open，闸门层 fail-closed。**
- Warden 是安全闸门 → 检查失败必须 BLOCK（现状，不动）。
- Advisor 是参谋 → LLM 挂了/超时/解析失败 → 返回 None → 主流程照跑，日志记 `advisor unavailable`。**LLM 永不 block 主流程**——这是保住"无人值守可靠性"的底线（参考 08-14 的 24 小时白跑事故：附加分析失败绝不能中断主流程）。

---

## 2. 每个 agent 的"思考点"设计

原则：**思考不一定要影响流水线，但一定要有痕迹**（advisor 文件 + memory 反思区 + auto-log 一行）。

### 2.1 Planner（tools/planner.py + agent_analyze.py）

| 思考点 | 落点 | 思考什么 | 输出 |
|---|---|---|---|
| **入口参谋** | `planner.analyze_level()` 拿到 `combo/judge/probes` 之后、return 之前 | 打包 `{组合WR, 缺口(gaps), 目标, 判定reasons, 探针数}` 问：这关当前的问题是什么？下一轮优先修哪一段？ | `advisor/planner_<lv>.json`：`{problem, priority_tier, note}`，≤150字。不改流程 |
| **轮末反思** | auto_loop 收尾（见 §5 反思环） | 本轮探针预期 vs 实际，下轮探针设计怎么改进 | memory 反思区 |

### 2.2 探针设计（tools/design_probes.py）—— 用户最看重，详见 §3

### 2.3 Judge（tools/judge_level.py）

| 思考点 | 落点 | 思考什么 | 输出 |
|---|---|---|---|
| **边界裁定建议** | `judge_with_rounds()` 判定完成后、写轮次前，仅在灰色地带触发（§4） | 这个 gap/偏差贴线案例该按哪态看？ | `advisor/judge_<lv>_<ts>.json`：`{recommendation, confidence, rationale}`。**result/rounds/action 一律不变** |
| **轮末校准反思** | 反思环 | 我的边界建议 vs 用户最终裁定是否一致？ | memory 反思区（校准 prompt，不改规则） |

### 2.4 Warden（tools/warden.py）

| 思考点 | 落点 | 思考什么 | 输出 |
|---|---|---|---|
| **W10 改法建议** | `check_probe_direction()` 产出 warn 后 | W10 已查出"方向不对"，但它不知道"怎么改对"。把缺口档+探针配置打包问 LLM：朝哪改（sd/of 量级建议） | `advisor/warden_<lv>.json`。**闸门结果不变**（warn 仍 warn、block 仍 block） |
| **低频有效性反思** | 跨轮反思（每 N 轮） | 最近安全事件里哪些检查在空转/该升级 | memory 反思区 |

### 2.5 Curator（tools/curator.py）—— 最便宜的改造，Step 1 就做

| 思考点 | 落点 | 思考什么 | 输出 |
|---|---|---|---|
| **统计→解读** | `detect_patterns()` 拿到 Counter 后、写 memory 前 | 这段日志暴露了什么模式？最值得关注的是什么？ | memory.md 的「反思」区（与现有数字统计区分：统计是数字，反思是判断） |
| **违规根因猜测** | `supervise()` 发现违规后 | 违规项可能的根因 + 建议查什么 | advisor/curator_<ts>.json |

**约束**：LLM 解读**不写 rules.json、不改 memory 的规则段**——只写反思区建议，规则改动仍须用户/主 agent 确认（系统基因：单一真源）。

---

## 3. 探针设计 LLM 化（核心）

现状链：`analyze_gaps()` → `_derive_needs()` → `plan_specs()` → `find_candidates()` → `fill_remaining()` → `finalize()` → `design()`。这条链承载了大量用户裁定（反推法、5槽全用、缺口驱动、配置不绑定档位、sd→WR 方向先验），**绝不重写**。

### 3.1 双层设计：规则生成（主） + LLM 审校（参谋）

**Phase A（Step 2，零风险）：探针方案审校**
- 落点：`design_probes.design()` return 之前（5 槽探针已生成完整后、Warden 前）。
- 输入（结构化瘦身，不传全量池子）：每档需求 `needs` + 覆盖 `covered` + 5 槽配置 `(sd/sc/ratios/of)` + 各自标 WR + 池子统计（verified 数、WR 范围、缺口段）+ 判定 reasons。
- 输出（JSON）：`{assessment, concerns[], suggestions: [{slot, action, reason}]}`。
- **规则校验兜底**：LLM 建议**不直接改探针**。建议若被采纳，仍走 `apply_probes` 前的 Warden 闸门（W02/W09 block、W10 warn）；JSON 非法/字段越界 → 丢弃建议，用脚本方案。
- 人在环时，主 agent 读 advisor 文件把建议带给用户；无人值守时只落盘，不生效。

**Phase B（Step 3）：探针有效性回测 → 让数据评价 LLM**
- 建回测表 `project-state/probe_hitrate.json`：每轮批跑后（dump_level_pools 后）回填每槽探针实际 WR vs 目标段。
- **离线 A/B**：`scripts/probe_ab_offline.py` 对**历史已入库关**重放——同一历史输入，脚本方案 vs 脚本+LLM 审校方案，比命中率。**不占 bot 算力**（400 局/轮才是最大成本，离线回放零成本）。
- 这是"怎么评估 LLM 设计的探针比脚本好"的**客观答案**：不是让 LLM 自评，是让历史数据说话。指标：
  - 探针命中率 = 实际 WR ∈ [目标±5] 的槽占比
  - 单轮修好率 = 一轮后 不合格→合格/接近 的比率
  - 有效信息率 = 新增、非重复、非 test 残留的数据点占比

**Phase C（Step 4，由 Step 3 数据决定是否走）**：LLM 参与缺口推导——仅当 `plan_specs` 返回 0 探针或"覆盖看似够但组合拼不出"这类模糊案例时，邀请 LLM 给替代探针方向，仍过 Warden。是否走到"LLM 当主角"（B 方案）由回测数据决定，不预设。

### 3.2 为什么"审校"而不是"让 LLM 直接设计"

- 用户多次裁定过的探针铁则（反推法、5 槽全用、缺口优先、sd 方向先验）是**踩坑换来的**，LLM 一次对话学不会也记不牢（L136 高 sd 是容易区的反直觉案例，LLM 大概率会错）。
- LLM 的价值不在"从零设计"，而在**跳出现有规则盲区**——比如"池子看着覆盖了但组合拼不出"（L163 教训）、"同一缺口两轮都没修好，该换思路"。
- 先让 LLM 当审校攒数据（Step 3 的回测），**证明它有用再放权**——这是对用户"不过度设计、可靠优先"偏好的直接回应。

---

## 4. 判定边界 LLM 化

用户痛点："合格/接近但继续调/明显改关卡，有时不能完全标准化。"——对应系统里已有 L152（9.99 vs 10）、L153（12.9 vs 15 用户裁定接近）、L158/L188（目标偏差贴线漏报）等案例。

### 4.1 灰色地带触发条件（全可配置，默认保守）

`rules.json` 新增 `judge_advisor_bands`（fail-loud：缺失即不触发，不默认开启）。在 `judge_with_rounds()` 判定后检查：

| 触发 | 条件 | 对应历史案例 |
|---|---|---|
| gap 贴线 | 任一 gap ∈ [ok_lo − tolerance_pp − 3, ok_lo − tolerance_pp) | L176 / L152 |
| 接近带边缘 | 任一 gap 刚过接近线下限（±2pp 内） | L153 |
| 目标偏差贴线 | 任一 dev ∈ {5, 10} ±2 | L158 / L188 |
| 6 轮临界 | 第 5 轮仍不合格，下轮触发改关卡 | 该问"再给一轮探针还是改关卡" |

### 4.2 参与方式

- 输出 `advisor/judge_<lv>_<ts>.json`：`{recommendation: "合格/接近/不合格", confidence, rationale}`。
- **规则永远是主判**：`result`、`rounds`、`action` 全部不变。LLM 输出只进 advisor 文件 + auto-log 一行 `[advisor]`。
- 为什么不让 LLM 自动改判定：判定权威是 Excel 目标 + verified 数据 + rules.json（单一真源）；用户明确"判定永远用通关率""标准里没有的指标不许 agent 用来排序"。LLM 的价值 = **提前把边界案例挑出来给人看**，把"用户逐个盯 30 关"变成"只看 LLM 挑出的 2-3 个边界"，最终仍由用户裁定（L153 就是用户裁的）。

---

## 5. 反思优化机制（agent 反思环）

复用现有收尾位置：auto_loop 每轮结束调 curator.py。新增 `scripts/reflect.py`（Step 1 先做单轮版）。

**单轮反思**（每轮结束，可配置 `reflect_every_n_rounds`，默认每轮）：
1. 收集材料：本轮 auto-log 段 + probe_configs 变化 + 判定结果 + advisor 文件。
2. 一次批处理调用（多 agent 问题打包成一次 prompt，控 token），每个 agent 一个问题：
   - planner：本轮探针预期 vs 实际（探针命中率），下轮怎么改？
   - judge：本轮边界裁定建议，哪些准/不准？
   - warden：本轮有无 W10 warn，方向检查够不够？
   - curator：本轮统计暴露了什么模式？
3. 输出：每个 agent ≤200 字反思 + 1 条可执行建议 → 追加到 `agents/<role>/memory.md` 的「反思」区（与 curator 数字统计区分开）。
4. 纪律：**反思产出只进 memory/advisor，永不自动改代码/规则**。memory 反思区滚动保留最近 N 条（防膨胀——项目已有防文件膨胀教训）。

**跨轮反思**（每 N 轮或手动）：
读各 agent 反思区 + 探针回测表，LLM 产出"过去 N 轮最值得改的 3 件事"，给人/主 agent 决策——这是 design_probes/rules.json 演进的输入，但改动仍须人确认。

---

## 6. 落地顺序（4 步，每步独立可交付、可回退）

| 步骤 | 内容 | 耗时 | 验证 | 回退 |
|---|---|---|---|---|
| **Step 1** | ① `tools/llm_client.py` + `llm_advisor.json` 开关 + `llm_usage.jsonl` 记账 ② curator 统计→解读 ③ planner 入口参谋 | 1-2 天 | 跑一轮 auto_loop（或手动 planner）：主流程结果与改造前**逐字节一致**；advisor 文件生成；token 可查；kill LLM 端点后主流程照跑 | 关开关，零代码回退 |
| **Step 2** | ① 探针审校 Phase A（`design()` return 前）② 判定边界触发 + advisor（`judge_with_rounds` 内）③ W10 改法建议 | 2-3 天 | 离线重放历史关卡审校，人审建议质量；跑 1 批（1 关×1 轮）全流程；Warden 兜底不破 | 关开关 |
| **Step 3** | 探针有效性回测表 + `probe_ab_offline.py` 离线 A/B | 1-2 天 | 跑评估脚本，对比脚本 vs 脚本+LLM 审校的命中率 | 只读脚本，无副作用 |
| **Step 4** | 跨轮反思 + 人在环"展示 advisor→确认采纳"流程固定化；**是否走 B 方案（LLM 当主角）由 Step 3 数据决定** | 1-2 天 | 数据说话 | 关开关 |

顺序逻辑：先建基础设施和零风险点（1）→ 再上用户最看重的探针审校 + 判定边界（2）→ 用数据证明 LLM 值不值（3）→ 最后才谈放权（4）。

---

## 7. 可靠性与成本控制

**可靠性（延续 fail-closed/fail-loud 基因）：**
1. **参谋层 fail-open**：LLM 失败/超时/解析失败 → None → 主流程照跑。与 Warden 的 fail-closed 明确区分（Warden 是闸门必须 fail-closed；advisor 是参谋必须 fail-open）。
2. **规则是唯一真源**：LLM 不写 rules.json、不改判定结果、不直接落探针；探针建议要生效必须走既有 `apply_probes` + Warden + 用户确认链。
3. **输出 schema 校验**：JSON 模式 + 字段白名单 + 数值越界检查，非法即弃。
4. **可回滚**：advisor 只追加；总开关一键关停；memory 反思区可清空。
5. **审计**：llm_usage.jsonl 全量记账。

**成本（用户敏感）：**
1. **便宜模型**：直接用现有 flash 模型（实测 ~113 token/次纯文本；推理型模型有 reasoning_tokens，prompt 里要求简短输出）。
2. **硬上限**：`llm_advisor.json` 配 `max_calls_per_round`（默认 5：planner 1 + probe 1 + judge 边界 ≤2 + curator 1），超了本轮不再调。
3. **触发保守**：判定边界只在灰色地带触发，不是每关都调。
4. **批处理**：多关卡/多 agent 问题打包成一次调用，不逐关逐 agent 调。
5. **输入瘦身**：只传结构化摘要（needs/covered/specs/reasons/池子统计），绝不传全量池子。
6. **缓存去重**：同关卡同轮次同输入 hash 命中不重复调。
7. **离线回放**：A/B 评估用历史数据，不占 bot 算力（400 局/轮才是大头）。
8. 预估：每轮 ~5 次 × 1-2k token ≈ ≤10k token/轮；一个月几十轮也就几十万 token 量级，flash 模型成本可忽略，相对 bot 跑批的算力/时间成本是零头。

---

## 8. 当时方案的职责边界

改造后的系统是**三层架构**：确定性执行内核（Planner/Judge/Warden/Curator 脚本）+ LLM 参谋层（advisor/反思）+ 人（最终裁定）。

当时设想为：规则生成候选，LLM 提供受限建议，Warden 拦截违规，真实数据验证结果，用户批准规则变化。离线 A/B、Judge 边界推荐和 memory 反思区均未形成现行生产能力，不作为当前说明。
