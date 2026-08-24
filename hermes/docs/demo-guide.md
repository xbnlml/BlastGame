# BlastGame 10 分钟演示指南

> 目标：不用 Unity、不用 bot 批跑，用**仓库内已积累的真实数据**（100+ 关 × 每档 240-400 局 bot 实测）重放"数据闭环"的下半段：选档 → 判定 → 一致性验证。
> 30 秒速览：`python scripts/demo.py`

## 0. 环境准备（一次性）

```bash
cd hermes/
python -m venv .venv && .venv/Scripts/activate   # 可选：独立环境
pip install openpyxl                              # 工具链唯一第三方依赖
```

不需要 Unity、不需要 GPU、不需要任何密钥。`stage-data/` 已含全部历史数据。

## 1. 冒烟验证（30 秒）

```bash
python scripts/smoke_test.py
```

预期：15/16 通过（唯一"失败"是 L120 未入库验证——那是**预期现状**：L120 asset 是预填槽位、尚未调优，不是 bug）。

## 2. 全自动调优脚本可以启动（1 分钟）

```bash
python scripts/auto_loop.py --help
```

看全自动闭环的参数（探针轮 400 局 + 贝叶斯提前停 + 验证轮 400 局）。**不实际运行**——真实运行需要 Unity 工程 + bot。

## 3. 数据闭环 Demo（5 分钟）

数据链：`stage-data/`（实测数据池）→ `tools/find_best_combo.py`（选最优五档组合）→ `tools/judge_level.py`（判定语义）→ `tools/state_snapshot.py`（全局状态）→ `tools/compare_level_db.py`（落库一致性）。

```bash
# ① 目标真源（Excel 是唯一权威）
python tools/read_target_wr.py 86,108,119,122

# ② 从真实实测数据池选最优组合（选档算法：档差可接受带 + DB 全绿优先）
python tools/find_best_combo.py 86,108,119,122

# ③ 判定引擎（gap 语义 / 目标偏差 / 接近 vs 合格）
python tools/judge_level.py 86,108,119

# ④ 全局状态快照（board 状态 + 每关最优五档）
python tools/state_snapshot.py --levels 51,86,108,119,143

# ⑤ 入库一致性验证（asset 参数 ↔ DB winRate ↔ 池子三方对账）
python tools/compare_level_db.py --levels 86,108
python tools/verify_asset_db_match.py --levels 86,108
```

预期：① 输出目标表格；② 每关输出五档 WR/配置/gaps/品质分；③ 输出判定结论（合格/接近 + 具体原因）；④ 每关一行状态；⑤ 输出 `✅ 基本一致` / `严格一致`。

## 4. 回归测试（1 分钟）

```bash
python -m unittest discover -s tests/pipeline -p 'test_*.py' -q   # 101 项
python tests/test_judgment_regression.py                          # 历史裁决固化
python tests/test_quality_score.py                                # 选档质量分
```

## 5. 文档地图

| 想了解 | 看什么 |
|---|---|
| 系统架构 / 数据闭环 / AI 介入边界 | `README.md` |
| 为什么这么设计（8 个 ADR） | `docs/design-decisions.md` |
| 工具索引（按"想做什么"查） | `tools/README.md` |
| 数据可靠性体系 | `tools/verify_pool_data.py` + `docs/design/knowledge-layer-architecture.md` |
| 目标胜率设计 | `docs/design/target-winrate-design-20260814.md` |
| RAG 检索学习项目 | `rag/`（python 3.11 + `pip install -r requirements.txt`） |

## 边界说明（诚实声明）

- **不能复现的部分**：Unity bot 实测环节（`scripts/submit_batch_unity.py`）依赖 Unity 工程 + License + 游戏资产，不在本仓库内；演示用已有实测数据重放下半段。
- **数据是真实的**：`stage-data/` 每关 240-400 局 bot 实测记录，带 BoardFingerprint / 来源分级 / 时间戳；board.md 与 Excel 记录了跨 3 周的真实入库轨迹。