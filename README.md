# BlastGame

贝塔项目4，炮台放置消除休闲游戏。

本仓库是 BlastGame 的 AI 辅助调优项目，使用 Hermes Agent 进行游戏难度自动化调优。

## 项目结构

```
BlastGame/
├── .gitignore
├── README.md
└── hermes/              ← 所有 Hermes 工作内容
    ├── tools/           ← Python 工具链
    ├── scripts/         ← 提交脚本
    ├── project-state/   ← 项目文档
    ├── stage-data/      ← 跑分数据
    └── .hermes-blastgame/ ← Hermes profile（配置、skill、计划）
```

## 使用

克隆后进入 `hermes/` 目录，运行工具脚本即可。
