# 动手前检查清单

任何非 trivial 任务必须走完此清单。

## 第零步：加载 skill

```bash
skills_list(category="game-design")
skill_view(name="blastgame-level-optimizer")     # 流程
skill_view(name="blastgame-multi-tier-designer") # 规则库
skill_view(name="blastgame-bot-orchestrator")    # 批跑
skill_view(name="blastgame-judgment")            # 判级
```

## 第一步：确认模式

- 讨论模式（默认）：展示方案 → 等确认 → 执行
- 全自动模式（用户说"你搞定"）：不展示不等不问，入库仍等确认

## 第二步：读数据

```bash
python tools/preflight.py submit --levels LV --tiers T
python -c "from tools.asset_patcher import read_ddc; print(len(read_ddc(LV)))"
python -c "from tools.data import pool; print(len(pool.dedup_records(pool.get_preferred_records(str(LV)))))"
```

## 第三步：查规则（设计探针前必做）

```bash
skill_view(name="blastgame-multi-tier-designer", file_path="references/probe-design.md")
```

核心问题：
- 参数合规？sc=ratios个数、ratios全相同等价
- 难度合规？Normal=3档(T1=T2,T4=T5)
- 数据源合规？不预过滤，传全部 recs
- 缺口评估？每档目标 vs 已有 bot WR，≤5pp=已覆盖

## 第四步：提方案前自检

1. ✅ 我加载了 skill 吗？（就是现在）
2. ✅ 参数理解正确？sc 是精细度不是难度、sd 不保证单调、of 方向不定
3. ✅ 对游戏机制理解正确？炮台自动射击不是手动瞄准、子弹数=方块数、没有步数。设计非调优类任务先读 `references/game-mechanics-overview.md`
4. ✅ 探针有已验证的 bot400 数据吗？（有→去掉）
5. ✅ 缺口评估对了？不是"哪数据少打哪"，是"哪个标准不满足解决哪"
6. ✅ 展示全量+备选+难度标注？
7. ✅ 这个配置是讨论好的还是我选的？（入库=讨论好的）

## 第五步：提交前验证

```bash
python tools/preflight.py submit --levels LV --tiers T
```

- board.md 的关键词是 "入库/待调优/改关卡"
- `preflight.py` 的 `get_board_levels()` 必须匹配 board.md 的关键词
- **回读验证（防 tier 映射 bug）：** `python -c "from tools.asset_patcher import read_ddc; print([(c['sd'],c['ratios'],c['of']) for c in read_ddc(LV)])"`，与 probe_configs 逐档比对。T1 配置必须符合预期，不一致则阻止提交
