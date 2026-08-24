# BlastGame — 数据驱动的游戏难度自动调优平台

贝塔项目4：炮台放置消除休闲游戏。本仓库是 BlastGame 的 **AI 辅助关卡调优工程**——把"关卡难度调参"从人工手感变成数据闭环。

## 快速开始

```bash
cd hermes/
python scripts/smoke_test.py    # 30 秒冒烟验证：工具可跑、数据可读、判定可用
```

## 项目结构

```
BlastGame/
├── README.md         ← 本文件（入口）
└── hermes/           ← 全部工程内容（工具链 / 文档 / 数据 / 测试）
    ├── README.md     ← 主文档：架构、数据闭环、AI 介入边界（先读这个）
    ├── tools/        ← 40+ 分析工具（tools/README.md 有按"想做什么"查的索引）
    ├── scripts/      ← 自动化（auto_loop 全自动调优 / submit_batch 批跑 / smoke_test）
    ├── tests/        ← 回归测试（判定规则、质量分、pipeline）
    ├── docs/         ← 设计决策 / 调研 / 学习笔记（docs/INDEX.md 导航）
    ├── project-state ← 关卡状态 board.md / 判定规则 rules.json / 运行记录
    ├── stage-data/   ← 每关实测数据池（bot/summary/phase0/phase1/2 分级存储）
    ├── rag/          ← 双层检索学习项目（BM25 + 向量）
    └── 手动挑配置记录.xlsx ← 入库配置记录（每关 5 档 × 胜率 × 参数）
```

## 入口说明

1. **想理解系统怎么运作** → `hermes/README.md`（架构 + 数据闭环 + AI 介入边界）
2. **想查"某个操作用什么工具"** → `hermes/tools/README.md`（禁止手写脚本重复造轮子）
3. **想查"为什么这么设计"** → `hermes/docs/design-decisions.md`（8 个核心设计决策）
4. **想跑任何工具** → 从 `hermes/` 目录执行 `python tools/<工具>.py <参数>`

仓库不包含 Unity 客户端源码；本工程通过 Unity Batch Mode 调用 bot 实测，Unity 工程在独立目录。