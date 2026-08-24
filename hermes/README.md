# BlastGame — 数据驱动的游戏难度自动调优平台

一个把"关卡难度调参"从人工手感变成**数据闭环**的系统：职责模块监督 + 当前 Hermes Planner 选择探针 → Unity Bot 批量实测 → 数据分级入库 → 自动判定达标 → 一致性验证。已调优 100+ 关，每关 400–1000 局真实 bot 数据。

## 它解决什么问题

游戏关卡有 5 个难度档位（T1–T5），每个档位有目标胜率（如 normal 80/80/60/45/45）。调奥难点：每档配置（难度+洗牌参数）和胜率的关系是**非线性、不可解析**的，只能靠实测。本系统把这条链路自动化：

```
确定性候选生成 + 当前 Hermes 模型选择探针(Planner) → 写入 asset(apply_probes) → Unity Bot 实测(submit_batch_unity)
→ 数据入池(dump_level_pools) → 判定达标(judge_level) → 一致性验证(verify_asset_db_match)
```

核心不是"调参"，而是**保证每一步的数据可信**（时间防线、数据源分级、指纹校验）。

## 为什么有工程含量

| 特性 | 说明 | 验证方式 |
|---|---|---|
| AI 介入边界 | 当前 Hermes 模型每关每轮只选择 5 个合法探针候选；Warden/Unity/Judge/入库保持确定性 | `tools/llm_probe_pipeline.py` |
| 贝叶斯提前停 | 探针轮最多 400 局，adaptive-stop + min-runs=60；验证轮 400 局定终值 | `scripts/auto_loop.py --adaptive-stop` |
| 数据可靠性 | 时间防线（逻辑改版旧数据整批作废）、四级数据分级、asset 指纹防漂移 | `tools/verify_pool_data.py` |
| 探针缺口驱动 | 反推目标胜率 → 池子候选优先 → 邻近微调 → 才自设计（不浪费槽位） | `tools/design_probes.py` |
| 入库一致性 | asset = Excel = LevelDatabase 三方严格一致 | `tools/verify_asset_db_match.py` |

## AI 介入边界

AI 只参与 `auto_loop.phase_analyze` 的探针选择：

```text
Excel 目标 + verified/phase1/phase2 趋势 + 上轮 receipt WR
    → 确定性候选目录
    → 当前 Hermes 模型选择 5 个 candidate_id
    → Warden → apply_probes → Unity → CSV receipt → Judge
```

模型不可用或输出非法时自动回退现有 `design_probes.py`。AI 不判定、不重试 Unity、不写 asset/Excel/board/DB、不决定改关卡或入库。正式结果记录在 `project-state/ai_probe_metrics.jsonl` 和 `auto_loop_round_report.json`；不做 Shadow/Canary 或额外控制批跑。Planner decision 还绑定到 V3 `run.json/events.jsonl` 的 `decision_id`、`context_hash`、candidate→slot 映射和 request plan，篡改会在 Unity 前阻断。approved lessons 默认关闭；开启时只加载 `project-state/approved_lessons/planner.jsonl` 中 active、带证据、条件匹配且未过期的条目，旧 `agents/*/memory.md` 仍不读取。

## 快速验证（30 秒）

```bash
python scripts/smoke_test.py    # 16 项回归冒烟测试：工具可跑、数据可读、判定可用
python scripts/demo.py          # 67 秒数据闭环演示：目标→选档→判定→快照→一致性（只读）
```

想看"系统在真实数据上怎么工作"：跑 `scripts/demo.py`，或读 `docs/demo-guide.md`（10 分钟自助演示路径）。

## 目录地图

```text
hermes/
├── tools/           # 40+ 分析工具（README.md 有按"想做什么"查的工具索引）
├── scripts/         # 自动化脚本（auto_loop 全自动调优、submit_batch 批跑、smoke_test）
├── project-state/   # 关卡状态 board.md / 判定规则 rules.json / 轮次与运行记录
├── stage-data/      # 每关实测数据池（bot/summary/phase0/phase1/2 分级存储）
├── docs/            # 设计决策 / 调研 / 个人学习笔记
│   ├── design/      # 设计决策文档 design-decisions.md（核心！）
│   └── INDEX.md     # 文档索引
├── rag/             # 双层检索（BM25 + 向量，recall@1 81.6%，MRR 0.847）
├── agents/          # 角色 manifest 契约；旧 memory.md 仅作人读历史，不直接驱动 Gate/Judge
├── reviews/         # 算法/判定评审记录（设计决策的论证过程）
├── tests/           # 回归测试（判定规则、质量分、pipeline 全套）
└── 手动挑配置记录.xlsx # 入库配置记录（每关 5 档 × 胜率 × 参数）
```

## 常用命令

- 全自动调优：`python scripts/auto_loop.py --levels 136,176 --tiers 1,2,3,4,5 --adaptive-stop`
- 单关现状：`python tools/stage_status.py 172`（全局汇总）或 `python tools/state_snapshot.py 172`（逐关快照）
- 最优组合：`python tools/find_best_combo.py 172`
- 判定：`python tools/judge_level.py 172`
- 入库：`python tools/reimport.py --config tools/reimport_xxx.json`

**做任何操作前，先查 `tools/README.md` 的工具索引**——按"你想做什么"找现成工具，禁止手写脚本重复造轮子。