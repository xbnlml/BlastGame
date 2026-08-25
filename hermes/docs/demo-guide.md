# 本地快速体验

## 离线 Replay

从 `hermes/` 目录运行：

```bash
python -m pip install openpyxl
python scripts/demo.py
```

该命令读取 `tests/fixtures/demo_replay.json` 中固定的真实 verified 数据快照，重新执行最优组合搜索和三态判定。它不读取 Unity、目标 Excel、LevelDatabase、用户目录或密钥，也不修改轮次和项目状态。

成功输出包括：

```text
evidence_sha256=<证据文件哈希>
OFFLINE REPLAY PASS: 4/4 levels
```

每关同时打印候选记录数、累计局数、目标 WR、算法重新选出的 WR 和 Judge 结论。SHA-256 用于标识当前证据文件版本；JSON/schema 无效或重放结果与 expected 不符时返回非零退出码。

## 本机工具链冒烟

有独立 Unity 工作区时运行：

```bash
python scripts/smoke_test.py
```

它只读检查 Python 编译、asset↔LevelDatabase、数据库/池对比、批次统计、Warden CLI 契约、探针设计和 auto_loop CLI。真实 Warden 提交闸门由 preflight 调用，不在 smoke 中伪造提交。该入口依赖独立 Unity 工作区；任一检查失败都会返回非零退出码。

工作区解析顺序：环境变量 `BLASTGAME_REPO` → 当前 checkout（若本身是 Unity 项目）→ 当前用户 `Documents/BlastGame`。Unity 项目位于其他位置时，请显式设置 `BLASTGAME_REPO`。

## 全自动入口

```bash
python scripts/auto_loop.py --help
```

真实批跑需要 Unity 工程、License 和游戏资产。离线 Replay 只复现“已有实测数据 → 选档 → 判定”部分，不伪装 Unity 模拟已经在当前机器执行。

## 回归测试

```bash
python -m unittest discover -s tests/pipeline -p 'test_*.py' -q
python tests/test_judgment_regression.py
python tests/test_quality_score.py
```

## 继续阅读

| 内容 | 文档 |
|---|---|
| 系统流程和 AI 边界 | `README.md` |
| 设计取舍 | `docs/design-decisions.md` |
| 操作入口 | `tools/README.md` |
| 当前关卡状态 | `project-state/board.md` |