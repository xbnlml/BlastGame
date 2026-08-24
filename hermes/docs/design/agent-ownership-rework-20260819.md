# Agent 责任化改造方案（历史 V2 设计稿）

> ⚠️ **当前实现以 2026-08-20 评审收敛版为准，不按本文旧的 memory 注入/独立事件流方案执行。** 当前方案复用 `ContextV3` 与 V3 `RunStore`，使用角色 `manifest.json` 契约；旧 `agents/*/memory.md` 不直接进入生产 Gate/Judge。Planner decision provenance 已接入 `run.json/events.jsonl`。本文保留为历史设计与评审记录。

## 0. 一句话方案

每个 agent 负责一个环节（planner=探针方向 / judge=判定权威 / warden=安全闸门 / curator=经验沉淀 / runner=批次运行），**监督运行、记录问题、按"分级落地"机制迭代自己的标准**。当前 LLM 只在探针设计这一个节点参与；其余全部确定性。批次参谋、Shadow、Canary 和第二套执行链暂不做。规则变更统一走 `apply_proposal.py`（唯一入口 + 契约测试门禁 + 可回滚）。

## 1. 用户动机（原话要点）

> "每个agent负责一个环节的工作，监督环节的运行，记录这个环节出现的问题，能够每个agent对自己负责的部分自动迭代，不管是流程标准还是skill memory。这样分多个agent才有意义，也有一些ai的应用。"

## 2. 现状问题（已查证）

| Agent | 实际工作 | AI | Memory 消费者 |
|---|---|---|---|
| planner | 编排脚本 | ❌ | 无（curator 写、无人读） |
| judge | 规则判定 | ❌ | 无 |
| warden | 规则扫描 | ❌ | 无 |
| curator | 正则统计 | ❌ | 无（auto_loop 调用但输出被吞） |
| Hermes | 人在环决策 | ✅ | 手动 delegate 时读 memory |

**核心顽疾**：memory 无消费者（批判评审实证：唯一读写方是 curator 自己）、agent 是角色命名的脚本、无人值守时系统无 AI。LLM 点在草案里 4 个，评审收敛为 **2 个真点**（其余是仪式感，检测对象确定性可得）。

## 3. 四 Agent 责任 + 监督点（评审收敛版）

### Planner agent —— 负责"探针方向"（AI 点：探针设计）
- 监督（确定性钩子，指到 auto_loop/tools 具体位置）：
  - P01 probe_present：`auto_loop.py:767` `phase_analyze` 返回后，验每关 probes≥5槽+combo+judge 字段齐全（失败→record + 驱动 L776 fallback_design_probes）
  - P02 probe_novel：`probe_configs.json` 写盘前，5 槽四元组 vs 黑名单（教训库 L1 邻近域匹配）vs 上轮 used_keys 碰撞检测
  - P03 probe_direction：warden.py W10 输出 warn 级方向错误 → 入问题库
  - P04 llm_usable：`llm_probe_pipeline.design_probes_llm()` 读 `llm_client.available()` + `llm_advisor.mode`，None（fail-open）→ record(llm_fallback_script) 走脚本兜底
  - P05 hitrate_tracked：`probe_hitrate.record_round()` 从 round_report 算三维评估（新边界信息/方向正确率/收敛贡献）
- 记录：命中率、方向错误案例、LLM 回退次数 → 问题库
- 迭代：探针设计标准（铁则/教训库域半径）按命中率提案（LLM 参与，走分级落地 L1）

### Judge agent —— 负责"判定权威"（LLM 点=0 判定调用，纯确定性）
- 监督：J01 verdict_emit（判定输出完整性）、J02 **确定性边界报告**（gap∈容差带内案例，精确数值+现行规则+历史锚点 L152/L54/L158，随 round_report 给人看）、J03 用户裁定回流记录
- 记录：边界案例库 + 用户裁定回流（decisions.jsonl）
- 迭代：用户裁定 → 变规则（20 天唯一验证有效的进化路径）。新增 `apply_proposal.py --from-ruling` 直连通道：用户裁定伴随明确规则意图时主 agent 直接生成变更请求（跳过 LLM 归纳），仍走四道门+diff 展示
- **LLM 不碰判定**：约束写死（评审一致），LLM 猜判态=制造标准外个案裁决，正是用户 20 天来最反感的漂移方向

### Warden agent —— 负责"安全闸门"（LLM 点=0，纯确定性）
- 监督：W01-W10 现有闸门全保留；新增违规模式写盘白名单扫描（白名单外写盘=原样 diff 呈用户，零 LLM）
- 记录：违规模式库、误拦/漏拦
- 迭代：检查规则按新模式增补（提案制，L1 待确认；安全冲突默认 warden 胜）

### Curator agent —— 负责"经验沉淀"（纯确定性，解读归批次参谋）
- 监督：C01 日志完整性、C02 模式统计（**废除正则空洞计数，改读 round_report**）、C03 时序检查（**废除坏正则时序，批判评审实证挂了半个月的误报**）
- 记录：模式库 → 提案给各 agent（有消费者：批次参谋/主 agent 确认）
- 迭代：批次末 LLM 把统计升级为解读（归入批次参谋），提案走 L1

### Runner agent —— 新增，负责"批次运行可靠性"（纯确定性零 LLM）
- 监督：Phase3/4（submit_batch_unity + dump）运行异常、CSV 落盘验证（P0-2 已落地）、Unity 心跳（P1-3）
- 记录：批跑异常、产出缺失
- 迭代：批跑参数/重试策略提案

## 4. Memory 双层机制（评审收敛，解决"无消费者"顽疾）

```
标准层（agents/<role>/rules.md 结构化 YAML）：
  └ 消费者 = 脚本（确定性加载）→ auto_loop 对应阶段读并据参调参
     （日志 [MEMORY] loaded 行；judge/warden 加载点做版本哨兵/注册表比对）
叙事层（agents/<role>/memory.md 自由文本 + 反思区）：
  └ 唯一消费者 = 批次参谋（LLM 每批 1 次注入 prompt，读全批 round_report + 各 agent 叙事层）
     （禁止 delegate_task 手动注入兜底、禁止每轮读 memory 调 LLM）
```

关键约束：**记忆必须有真实消费者**，落代码层不落概念层；标准层给脚本、叙事层给批次参谋，双轨不混。

## 5. 迭代闭环（分级落地，解决"人确认与无人值守冲突"）

```
监督（确定性）→ 记录（问题库 events.jsonl）→ 分析（LLM 或确定性）→ 提案（proposals/）→ 分级落地 → 生效验证
```

| 级别 | 内容 | 何时可执行 |
|---|---|---|
| **L0 自动** | 事件/审计痕迹/教训库只追加、白名单写盘 diff 留档 | 无人值守期间直接执行，无需确认 |
| **L1 待确认** | rules.json 阈值/severity 变更、agents rules.md 标准变更 | 无人值守期间积累为 pending 提案 + 预跑冲突检测与契约测试 dry-run，用户返回批量确认/回滚 backlog |
| **L2 自动+后验** | 仅 3 类机械可验证变更：①容差带内数值微调且历史判定回放 result 不变 ②新增"只记账不拦截"影子检查 ③教训库追加只增不删 | 自动落地；每次写快照+附契约测试结果+下次批次回滚位；preflight 发现回放断言失败→自动回滚上一 _meta 序列号并告警 |

**冲突仲裁**（评审 P2 补丁）：跨 agent 建议冲突默认 **warden 胜（安全优先）**；同域冲突（planner vs pipeline 教训库）以 pipeline 为准；仲裁记录进 advisor 可查。规则闸门和教训库互相喂养：LLM 方案被 W 闸门拦→miss/block 事件→复盘→提案扩教训库，闭环自洽。

## 6. 规则变更统一治理（唯一入口）

- 唯一入口：`apply_proposal.py`（新建）——所有规则/标准变更走它
- 门禁：test_judgment_regression + test_warden_negative + smoke_test + 历史判定回放
- 版本：_meta version 序列号 + changelog + `--rollback` 机械回滚
- 历史判定按 rules_version 时间切分打 legacy 冻结标签，防新阈值倒灌污染监督基线
- 写盘白名单：白名单外写盘 = 原样 diff 呈用户（零 LLM 判断）

## 7. 与探针 LLM 化的关系（评审收敛）

探针 LLM 化（probe-design-llm-final）是 **planner agent 的执行器**：
- pipeline=planner 的执行器（统一在 roles.json 名下），P04 走同一 llm_client，agent 标签归一
- `llm_advisor.json` 的 `mode=llm/script` 只控制探针选择器或确定性 fallback，不启动双通道批跑
- 教训库升级（邻近域 L1≤ε 泛化）由验证闭环自动增补
- 不冲突：探针 LLM 化先行落地（S2-S4），其余 agent 按同一"监督/记录/分级迭代"机制后续改造

## 8. 成本预算（评审收敛）

- LLM 调用面：仅 2 点——探针设计（每关每轮 1 次 ≤3K token）+ 批次参谋（每批 1 次，卡壳触发 +1 次，合计 ≤2 次/批）
- 成本强制走 llm_client（唯一入口 + usage 记账）、agent 级 enabled 键、月度 3,000 次熔断
- 估算：每批 17 关×6 轮 ≈ 102 次探针设计 + ≤2 次参谋 ≈ 30-60 万 token/批（比全量池子方案省 80%）

## 9. 落地顺序（评审收敛）

| 步 | 内容 | 验证 | 回退 |
|---|---|---|---|
| **S1** | roles.json + agents_supervision.py（监督钩子/问题库 events.jsonl）+ 记忆双层目录 | 每 agent 监督脚本单测；[MEMORY] loaded 日志 | 删文件 |
| **S2** | 探针 LLM 化（llm_client/聚合器/校验层/prompt——已部分落地）+ Warden 白名单扫描 | 影子模式并行不写盘 | 关开关 |
| **S3** | 分级落地机制（apply_proposal.py + 门禁 + 回滚）+ 用户裁定直连通道 | 契约测试 dry-run | 回滚 |
| **S4** | 批次参谋（读全批 round_report + 叙事层 → 简报/卡壳建议/规则空白） | 输出简报可读 | 关开关 |
| **S5** | runner 角色落地（批跑监督实际接入 auto_loop） | 异常捕获单测 | 不接 |

S1-S3/S5 纯确定性可立即做；S4/S6 等 08-21 配额重置后开 shadow 实测。

## 10. 对外叙事（改造后怎么讲）

四层架构：确定性执行内核（批跑/判定/闸门）+ 责任 agent（监督/记录/分级迭代）+ LLM 决策点（探针设计/批次参谋 2 点）+ 人（最终裁定）。

讲法："每个 agent 负责流水线的一个环节：监督它运行、记录它的问题、按分级机制迭代它的标准——无人值守时机械部分自动进化，有风险的部分积累给你确认。AI 只在两个真正需要判断的地方参与：探针怎么设计、批次结束后的综合参谋。规则依然是唯一真源，AI 的建议永远走人确认才落地的通道。"

---

*两轮交叉评审已收敛所有核心分歧（LLM 点数、分级落地、memory 消费者、仲裁机制、规则治理）。后续执行以本文档为准。*