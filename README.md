# BlastGame

炮台放置消除休闲游戏。本仓库是它的**关卡难度调优工程**：用程序+实测数据代替人工手感来调难度参数。

## 快速开始

```bash
cd hermes/
python -m pip install openpyxl
python scripts/demo.py          # 离线重放真实证据，不需要 Unity/密钥/外部文件
```

成功时输出 `OFFLINE REPLAY PASS: 4/4 levels`。本机同时有 Unity 工作区时，可运行 `python scripts/smoke_test.py` 检查 Excel、asset、数据库、Warden 和批跑入口。

## 当前验证快照（2026-08-25）

以下关卡的当前配置已经完成 asset、Excel、board、LevelDatabase 回读核验：

| 关卡 | 难度 | 状态 | 目标 WR | 当前 WR |
|---:|---|---|---|---|
| L58 | superhard | ✅已入库 | 70/55/40/25/15 | 68.8/54.2/39.7/28.8/18.8 |
| L79 | normal | ✅已入库 | 85/85/65/50/50 | 87.8/87.8/72.5/52.0/52.0 |
| L120 | normal | ✅已入库 | 80/80/60/45/45 | 80.4/80.4/58.5/45.2/45.2 |

完整状态以 [`hermes/project-state/board.md`](hermes/project-state/board.md) 为准；配置记录在 [`hermes/手动挑配置记录.xlsx`](hermes/手动挑配置记录.xlsx)，可复核数据在 [`hermes/stage-data/`](hermes/stage-data/)。

## 项目结构

```
BlastGame/
├── README.md         ← 本文件（入口）
└── hermes/           ← 全部工程内容（工具链 / 文档 / 数据 / 测试）
    ├── README.md     ← 主文档：流程、机制、LLM 参与范围（先读这个）
    ├── tools/        ← 分析工具（tools/README.md 按"想做什么"索引）
    ├── scripts/      ← 自动化（auto_loop / submit_batch / offline replay / live smoke）
    ├── tests/        ← 回归测试（判定规则、质量分、pipeline）
    ├── docs/         ← 设计决策 / 调研（docs/INDEX.md 导航）
    ├── project-state ← 关卡状态 board.md / 判定规则 rules.json / 运行记录
    ├── stage-data/   ← 每关实测数据池（bot/summary/phase0/phase1/2 分级）
    ├── rag/          ← 双层检索学习项目（BM25 + 向量）
    └── 手动挑配置记录.xlsx ← 入库配置记录（每关 5 档 × 胜率 × 参数）
```

## 入口说明

1. **想理解系统怎么运作** → `hermes/README.md`
2. **想查"某个操作用什么工具"** → `hermes/tools/README.md`
3. **想查"为什么这么设计"** → `hermes/docs/design-decisions.md`
4. **想直接验证核心算法** → `cd hermes && python scripts/demo.py`
5. **想跑任何工具** → 从 `hermes/` 目录执行 `python tools/<工具>.py <参数>`

仓库不包含 Unity 客户端源码；工具通过 Unity Batch Mode 调 bot 实测，Unity 工程在独立目录。