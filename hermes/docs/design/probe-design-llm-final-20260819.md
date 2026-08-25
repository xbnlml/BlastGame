# 探针 LLM 化最终定稿（两轮交叉审视收敛版）

> 日期：2026-08-20 · 状态：**正式接入现有 auto_loop**
> 关联：初稿 `probe-design-llm-20260819.md` | 批判评审 `agent-thinking-rework-critique-20260819.md` | 主导派方案 `probe-design-llm-final-20260819.json`
> 本文件为最终可执行版，冲突处以本文件为准。

## 0. 一句话方案

**LLM 每关每轮选择 5 个合法 candidate_id，规则做安全闸门，数据做裁判。** 确定性代码生成候选目录，Hermes 当前模型只选择候选并写实验假设；非法输出/模型失败立即回退现有脚本设计，不增加额外 Unity 批次，不做 Shadow/Canary。

## 1. 用户裁定（不可修改）

1. 探针方向无法只靠固定模板——每关情况不同、参数↔胜率非单调（L136 高 sd 反而是容易区），需要 LLM 参与选择
2. 全自动无人值守时探针设计需要 AI 参与，脚本不能独立完成
3. 即使 LLM 命中率暂时不如脚本，优化 LLM 方式方法，**绝不退回纯脚本**——这条路是对的
4. 非 verified 数据（phase1/2）量少误差大但**趋势可用**，必须作为 LLM 输入——不给全量池子数据不够
5. 设计理由全程记录（project-state/advisor/），用户要看时展示，不主动推送
6. 必须保证高效率和高质量

## 2. 架构总览（三层）

```
第 1 层：确定性候选生成 + Hermes 探针选择器（每关每轮 1 次）
   ↓ 输入=Excel目标、分层聚合、历史轨迹、合法候选目录
   ↓ 输出=5 个 candidate_id + rationale/evidence/hypothesis
   ↓ candidate catalog 校验 → 失败/超时脚本兜底
第 2 层：规则安全闸门（确定性，复用现有 Warden/铁则）
   ↓ 校验 5 槽完整、配置互异、未验证重复、字段合法
   ↓ 写盘唯一入口 apply_probes.py（AI 无旁路）
第 3 层：真实批跑反馈（数据裁判）
   ↓ 同一 receipt 的 CSV WR 回流 round_report
   ↓ 下一轮继续使用真实结果；不额外跑控制组
```

**核心变化**：LLM 参与探针方向和候选选择；脚本负责候选生成、合法性、写盘、批跑、判定和兜底。模型不能自由创造四元组，也不能改变判定标准。

## 3. 输入打包方案（分层聚合，防 token 爆炸 + 防伪精确）

### 3.1 预聚合器（确定性脚本做，LLM 只读摘要）
- 全量池子按 `数据源 × 参数桶` 聚合成条带式摘要：
  - **verified 带**（bot/summary/phase0）：每档每桶 WR 均值、样本数 n、极差、最近明细
  - **phase2 带**：标注 `±5-10pp 误差`
  - **phase1 带**：标注 `±20pp 误差`
- 每条数据行固定格式：`[源|档位|sd|sc|ratios|of|WR|n|样本日期]`，行首源标签 V2/P2/P1
- **单点 phase1/2 WR 永不作为目标值进输入**——只给桶均值+相对方向（杜绝拿噪声当真值）

### 3.2 属性级趋势命题（关键防偏差机制）
- 脚本自动提取参数→WR 方向命题：`sd↑→WR↓ (V2-x12, 一致11/12, STRONG)`
- 分级：**STRONG**（verified 为主多源同向）/ **WEAK**（仅 phase1/2 单源）/ **CONFLICT**（与 verified 矛盾，LLM 必须显式说明选择理由）/ **NON-MONO**（U 形/局部反转，L136 型，禁止线性外推）
- **P2 补丁**：方向判定要求相邻桶差 ≥5pp 且高样本桶权重更高；<5pp 标 FLAT；阈值按分位数动态取值；命题附拐点桶行 id

### 3.3 token 预算（硬约束）
- 单关单轮 ≤3K token（数据~2000 + 指令~500 + 输出~500）
- **P1 补丁**：桶级过滤（只输出 n≥3 且 games≥400 的桶，n<2 压缩为"样本不足"单行）；按 n×games 排序取 top-N；预算剩余 <200 删低置信桶；`probe_input_packager` 单测断言"任意输入输出必 ≤1000 token"
- 高熵字段（长 batch 串/deathProfile/failBucketDistribution）**不进 prompt**，落 JSON 附件按需检索
- 增量缓存：同关同轮聚合缓存，只有新批次落池才重算

### 3.4 数据使用铁律（写死在 prompt 数据契约段）
1. verified 决定目标段与精调方向
2. phase1/2 只回答"哪里可能存在值得探的空间"，未被 verified 支撑的方向结论按 WEAK 处理
3. CONFLICT 以 verified 为准，LLM 引用必须显式裁决
4. 非单调案例禁止线性外推
5. 收敛判定硬隔离——只吃 verified 数据，低置信数据不可能触发合格/接近/不合格

## 4. 五段式 prompt（模板 tools/prompts/probe_design_v1.txt，版本号入 advisor）

1. **角色与任务**：资深休闲游戏难度调优专家，产出 5 槽探针；明示"每轮都参与，本轮错的下轮会反馈修正，大胆尝试但要可解释"
2. **数据契约**：输入字段说明 + 数据使用铁律 + 铁则硬约束清单（每条附践坑来源）
3. **当前状态快照**：目标 Excel 真源、当前各档 verified WR、缺口 gaps、判定 reasons、历史轨迹≤3 轮、脚本参考答案（标注"仅参考，可采纳/改进/推翻"）
4. **教训库**（上轮教训段）：上轮配置→实测WR→失败原因结构化注入；禁令：不得设计 direction 相反或同域配置（邻近域泛化 L1≤ε 同拒）
5. **输出 schema 与格式**：JSON 结构 + rationale + evidence 引用（引用 Bn 行 id，校验器检查存在性）

## 5. 输出校验层（三重 + 打回链）

### 5.1 候选决策校验（写盘前必经）
| 校验 | 规则 |
|---|---|
| **identity** | 5 个 candidate_id 必须来自当前 catalog，snapshot/catalog hash 必须匹配 |
| **semantic** | candidate 不重复、不撞 verified 配置、不重复 deal fingerprint，证据必须属于该候选 |
| **execution** | 候选四元组由 catalog 提供；字段范围、W02/W09 和写盘检查仍由现有代码执行 |

### 5.2 打回链
- 违反铁则 → 打回重设计，**每次附具体错误回填进 prompt**
- 重试上限 3 次 → 全败 fallback 到现有确定性 `design_probes.design()`（已验证代码），绝不以非法配置出盘
- 全程记录 advisor（用户可查"为什么这次用了脚本方案"）

### 5.3 当前实现
- LLM 只选择候选，不自由生成四元组；候选不足或输出非法时回退 `design_probes.design()`。

## 6. 教训库（黑名单升级）

现状缺陷：probe_blacklist.json 的 key 是 (sd,sc,ratios,of) 精确字符串匹配，微调换汤不换药会漏（批判派确认的现存缺陷）。

升级为结构化教训库：
- 每条带 `{reason(判定原因: gap不足/目标偏差/硬违规), direction(参数应向哪侧移动), 实测WR, 轮次}`
- 邻近域泛化：配置空间 L1 距离 ≤ε 视为同域一并拒绝
- 教训注入 prompt 第 4 段；单样本教训标 low-confidence 只提示不强拦，Warden W09 兜底

## 7. 评估体系（正式批跑结果）

### 7.1 主指标改三维（P5 补丁，替代贴目标式命中）
| 维度 | 定义 |
|---|---|
| **新边界信息** | 实际 WR 落在未知区/黑名单边界/极值区 → +1 |
| **方向正确率** | 单独列，探针方向与实测方向一致率 |
| **收敛贡献** | 该槽是否让 不合格→接近/合格 |

贴目标只算辅助信号（1/3 权重）；新增负项"零信息槽"（实际 WR 落在已验证区间内）。

### 7.2 正式批跑指标
- `selected_candidate_ids`：本轮 AI 选择了哪些候选。
- `actual_wrs`：同一 receipt 的 campaign-summary 实际 WR。
- `judge_result`：确定性 Judge 结果，仅用于结果记录，不由 AI 产生。
- `script_fallback`：Hermes 不可用或决策非法的次数和原因。
- 业务验收：不增加 Unity 批跑次数、不增加重复配置，并逐步减少无效探针或达到合格所需轮数。

## 8. 正式运行与回退

| 模式 | 内容 |
|---|---|
| **llm** | 每关每轮调用当前 Hermes 模型选择 5 个 candidate_id |
| **script** | `enabled=false` 或模型失败时使用现有确定性探针设计 |
| **回退** | 关闭 `llm_advisor.json.enabled`，不改变 Warden/Unity/Judge |

不做 Shadow、Canary 或第二次 Unity 控制批跑；正式批次本身就是验证数据。

## 9. 可靠性（延续 fail-open/fail-closed 基因）

1. **参谋层 fail-open**：LLM 失败/超时/解析失败 → None → 脚本兜底 → 主流程照跑（08-14 白跑事故铁律）
2. **闸门 fail-closed**：Warden 检查失败必须 BLOCK（现状不动）
3. **规则唯一真源**：LLM 不写 rules.json、不改判定结果；探针要生效走既有 apply_probes + Warden + 轮次验证
4. **架构无旁路**：LLM 走 `llm_probe_pipeline.py`；写盘唯一入口 `apply_probes.py`；输出先过 candidate catalog、W02/W09 和 used_keys
5. **契约测试**：快照 analyze_gaps/_derive_needs/plan_specs 签名与返回结构，改动即红；交付门 = test_warden_negative + test_judgment_regression + smoke_test 全绿
6. **可回退**：总开关一键关停；advisor 只追加；所有新文件不触碰现有 tools 主路径
7. **成本**：单关单轮最多 3 次校验重试，usage 记账；不增加 Unity 批跑

## 10. 决策痕迹（四层 JSONL，防不可审查）

1. 输入快照（聚合数据全文 + 内容 hash）
2. 推理链（LLM 输出 reasoning 原样存档，绝不润色）
3. 决策+校验史（最终输出 + 被拒中间尝试 + 拒绝原因 + 重试史）
4. 回放审计（用输入快照 hash 重放确定性校验，机械区分"LLM 选错"vs"数据不支持"vs"校验拒错"）

自由文本自述一律标注"自述"不视为事实。

## 11. 职责边界

三层架构：确定性执行内核 + LLM 探针设计核心 + 人最终裁定。

探针设计由 LLM 在候选目录内做选择；规则负责安全闸门，批跑数据验证结果，用户负责最终入库或改关卡裁定。

可核验边界：
- "探针是 AI 设计的吗？" → 是。LLM 读分层数据设计目标段和参数，规则只校验违规不要求一致
- "怎么证明 AI 设计得好？" → 看正式批跑中的新候选、实际 WR、重复率、收敛轮数和 Unity 总局数；不额外跑控制批次
- "AI 会乱来吗？" → candidate catalog 校验 + Warden 闸门 + 脚本兜底，主流程永不中断
- "AI 能不能关闭？" → `llm_advisor.json.enabled=false`，立即回到现有确定性探针设计

## 12. 落地步骤

| 步 | 内容 | 验证 | 回退 |
|---|---|---|---|
| **S1** | `llm_client.py` + `probe_input_packager.py` + candidate catalog + Hermes 当前模型选择器 | fake Hermes 契约测试 + pipeline/Judge/Warden 回归 | `enabled=false` |
| **S2** | 接入 `auto_loop.phase_analyze`，记录 candidate IDs 与脚本 fallback | 不启动 Unity 的 adapter/validator 测试 | `mode=script` |
| **S3** | 正式调优批次直接验证：receipt WR 回流、重复率、收敛轮数、Unity 局数 | 真实 round report 和 `ai_probe_metrics.jsonl` | `enabled=false` |

**运行约束**：模型/provider 跟随 Hermes 当前配置，reasoning=max；模型不可用时脚本兜底。不启动额外 Shadow/Canary 批次。

---

*本文件由主 agent 汇总两轮交叉审视（主导派×批判派 × 再审视）收敛而成。关键分歧：R5 抄脚本不可见（未解→P4 补丁）、R8 可靠性（已解）、R2 伪精确（已解）。*