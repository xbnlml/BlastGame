# BlastGame — 贝塔项目4 多档位调优工具

关卡难度自动调优管道（Hermes Agent 驱动）。

## 快速入口

- **全自动调优：** `python scripts/auto_loop.py --levels 136,176 --tiers 1,2,3,4,5`
- **提交 Bot 批跑：** `python scripts/submit_batch_unity.py "<关卡>" --games 400 --tiers 1,2,3,4,5`
- **探针设计：** `python tools/design_probes.py 172 --write`（经 apply_probes 写入，Warden 闸门）
- **组合分析：** `python tools/planner.py --levels 136,176`
- **判定：** `python tools/judge_level.py 172`
- **批后审计：** `python tools/curator.py`（模式识别 + 监督）
- **Excel 入库数据：** `手动挑配置记录.xlsx`
- **关卡状态：** `project-state/board.md`

## 工具索引（重要）

**做任何操作前，先查 `tools/README.md` 的工具索引**——按"你想做什么"找现成工具，禁止手写脚本重复造轮子。

```bash
ls tools/            # 看有哪些脚本
cat tools/README.md  # 按操作类型查工具（写操作/只读/判定/批跑/agent 五类）
```

- **统一入库** → `tools/reimport.py` / `tools/reimport_batch.py`
- **写 asset** → `asset_patcher.py::write_ddc` + `verify_asset`
- **写 Excel** → `write_excel.py::write_tiers`（胜率列小数 0.8=80%）
- **生成 DB payload** → `tools/gen_payload.py --levels X`（别手写）
- **重选 vs Excel 对比** → `tools/compare_imported.py`
- **查单关现状** → `tools/level_status.py`

## 五角色体系

```
Warden（事前防护）→ Planner（决策）→ Executor/auto_loop（执行）→ Judge（裁定）→ Curator（进化+监督）
```

- 模块独立：agent_analyze.py / design_probes.py / judge_level.py 可单独使用
- agent 记忆：`agents/{warden,planner,judge,curator}/memory.md`
- 判定标准：`project-state/rules.json`（单一真理源）
- 系统 skill：`blastgame`（Hermes 系统目录，唯一权威）

## 目录结构

```
hermes/
├── tools/              # Python 工具（池子、探针、asset修补、判定、五角色）
├── scripts/            # auto_loop.py / submit_batch_unity.py
├── agents/             # 四 agent 记忆（memory.md）
├── stage-data/         # 数据池缓存
├── project-state/      # board.md / timeline.md / wrongbook.md / rules.json
├── auto-log/           # auto_loop 运行日志（curator 读取）
└── 手动挑配置记录.xlsx  # 入库配置记录
```

## 工作约定

- **动手前先查 `tools/README.md` 工具索引**，禁止手写脚本重复造轮子（写 asset/Excel/board/DB 前尤其要查）
- 不改 `$BLASTGAME_REPO` 下任何文件（除非用户授权）
- `funnel_b/` 是竞品关卡数据，不做参考源
- `test/` 是我们自己的关卡配置，Python 工具只写 test/
- 改动前先备份 asset，修复用 asset 自身或项目内的备份
- 禁止 git 命令（SourceTree 手动管理）

## 自动加载守则

`hermes/.hermes.md` 由 Hermes 每次自动加载（含"动作前守则"），是工具/经验复用的触发入口：
踩坑 → 追加进 `.hermes.md` → 下次自动触发，而不是塞进大 skill。全局 `blastgame` skill 是深度参考（按需加载）。
