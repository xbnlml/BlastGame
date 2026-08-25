# BlastGame — 关卡难度的全自动调优

关卡难度调参是个麻烦事：每个关卡有 5 个难度档位（T1–T5），每个档位对应一个目标胜率（如 normal 80/80/60/45/45）。问题在于，配置参数（难度+洗牌参数）与最终胜率之间是非线性、不可解析的关系——改一个参数，胜率往哪走只能靠实测才知道。

这个仓库把"改参数 → 跑实测 → 看结果 → 再改"做成可重复执行的自动循环：程序设计探针、写入配置、调用 Unity Bot、刷新数据池并判定是否达标；合格后停在“待确认入库”，最终落盘仍由人确认。`stage-data/` 保存 L51–200 的状态快照及现有可靠/探索数据，并记录来源、局数与时间。

## 流程

```text
确定性候选生成 + LLM 选择探针(Planner) → 写入 asset(apply_probes) → Unity Bot 实测(submit_batch_unity)
→ 数据入池(dump_level_pools) → 判定达标(judge_level) → 一致性验证(verify_asset_db_match)
```

## 关键机制

| 机制 | 说明 | 相关代码 |
|---|---|---|
| AI 介入边界 | LLM 每关每轮只选 5 个探针候选；Warden/Unity/Judge/入库全程确定性 | `tools/llm_probe_pipeline.py` |
| 贝叶斯提前停 | 每轮默认 400 局且可由 CLI 调整；第 1–5 轮可早停，第 6 轮跑满配置的 `--games` | `scripts/auto_loop.py --adaptive-stop` |
| 数据可靠性 | 同牌面历史批次可累积复用；有快照比牌面，无快照走时间防线，并按来源区分可靠/参考数据 | `tools/verify_pool_data.py` |
| 探针缺口驱动 | 反推目标胜率 → 池子候选优先 → 邻近微调 → 最后才自设计 | `tools/design_probes.py` |
| 入库一致性 | asset = Excel = LevelDatabase 三方一致 | `tools/verify_asset_db_match.py` |

## LLM 参与范围

LLM 只参与探针选择（`auto_loop.phase_analyze`），选择被限定在确定性候选目录内：

```text
Excel 目标 + verified/phase1/phase2 趋势 + 上轮实测 WR
    → 确定性候选目录
    → LLM 选择 5 个 candidate_id
    → Warden → apply_probes → Unity → CSV → Judge
```

模型不可用或输出非法时回退到 `design_probes.py`。LLM 不判定、不重试 Unity、不写 asset/Excel/board/DB、不决定改关卡或入库。每次决策记录在 `project-state/ai_probe_metrics.jsonl` 和 `auto_loop_round_report.json`。

## 快速验证

```bash
python -m pip install openpyxl
python scripts/demo.py           # 离线 Replay：真实证据→选档→判定，不依赖 Unity
python scripts/smoke_test.py      # Live Smoke：本机 asset/DB/数据与只读 CLI 检查
python -m unittest discover -s tests/pipeline -p 'test_*.py' -q
```

## 目录

```text
hermes/
├── tools/           # 分析工具（tools/README.md 按"想做什么"索引）
├── scripts/         # auto_loop / submit_batch / offline replay / live smoke
├── project-state/   # board.md 关卡状态 / rules.json 判定规则 / 运行记录
├── stage-data/      # 每关实测数据池（bot/summary/phase0/phase1/2 分级）
├── docs/            # 设计决策 / 调研（docs/INDEX.md 索引）
├── rag/             # 双层检索（BM25 + 向量）
├── agents/          # 角色 manifest 契约
├── reviews/         # 评审记录
├── tests/           # 回归测试
└── 手动挑配置记录.xlsx # 入库配置记录（每关 5 档 × 胜率 × 参数）
```

## 常用命令

```bash
python scripts/auto_loop.py --levels 136,176 --tiers 1,2,3,4,5 --adaptive-stop   # 全自动调优
python scripts/demo.py                                                              # 离线证据重放
python scripts/smoke_test.py                                                        # 本机工具链冒烟
python tools/stage_status.py 172                                                 # 汇总
python tools/state_snapshot.py --levels 172                                      # 单关快照
python tools/find_best_combo.py 172                                              # 最优组合
python tools/judge_level.py 172                                                  # 判定
python tools/reimport.py --config tools/reimport_xxx.json                        # 入库
```

做任何操作前先查 `tools/README.md` 的工具索引，按"你想做什么"找现成工具。