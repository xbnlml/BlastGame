---
name: blastgame-level-optimizer
description: "BlastGame 多档位全自动调优管道。全自动=三批流程（决策→执行→裁定），协操=按需调用单模块。"
version: 7.2.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [blastgame, game-design, level-optimizer, pipeline]
    related_skills: [blastgame-multi-tier-designer, blastgame-bot-orchestrator, blastgame-auto-pipeline, blastgame-judgment]
---

# BlastGame 关卡调优

> 工作目录：`D:\download\Hermes\`。游戏工程：`$BLASTGAME_REPO`。
> **加载：** `blastgame-multi-tier-designer`（规则）+ `blastgame-bot-orchestrator`（批跑提交）+ `blastgame-judgment`（判定）。

---

## 操作守则

0. **先加载 skill 再动手。** 新会话第一件事：`skills_list(category="game-design")` → `skill_view(name)` 加载相关 skill。skill 在系统目录 `~/AppData/Local/hermes/skills/` 下不在项目文件夹，不主动加载不存在。**不读 skill 就动手 = 等着被纠正。**
0a. **理解游戏机制后再设计方案。** 设计探针/任务/功能前，必须读游戏工程文档（`Blast_MainGame.md`, `Gameplay_Rules_Logic.md`, `Game_Score_Logic.md`）和实际 asset 文件确认机制。不要凭惯性猜测游戏类型（不是手动瞄准三消，是炮台自动射击 + 槽位 + 队列消除）。不理解机制就设计方案会被纠正。
1. **先方案再动手。** 操作前"计划：[操作]"→ 问"要执行吗？"
2. **先回答问题再执行。** 用户提问时先回答，不把问题当隐式指令跳过回答直接干活。
3. **展示结果再问下一步。** 执行完立即展示数据（表格优先），不跳到"继续？"
   **数据展示铁律：所有档位都列出来，每档标注 WR、目标差、sd、ratios、of、局数、数据来源（bot/summary/phase2）。** 不合标的档也要列，不只列"达标"的。
4. **全自动模式：** 不展示、不等、不问。入库仍等确认。
   **注意：已入库的关卡绝不再提交批跑！** 在 `board.md` 确认状态后再操作，避免浪费资源。
5. **禁止主动启动 Unity。** `submit_batch_unity.py` 是唯一提交流程。不调 `restart_unity.py` / `check_unity.py`。
6. **不做未要求的事。** 改 asset 就只改 asset，不自动继续提交流程。
7. **不一定同意用户。** 不合理时说出来。
8. **诊断优先 — 展示数据再说话。** 发现异常先完整展示数据对比，定位根因再提方案。不要在根因确认前拍脑袋加 workaround。不要只报症状（"T1 读错了"），要报证据（"asset 索引0=sd=15，但 CSV 中 T1 的 sd=55，对应索引4"）。**不要盲目同意用户的分析**——看完数据后独立判断，不一致时说出来。
9. **不凭记忆猜参数含义。** sd 非单调、sc 是精细度不是难度、全相同 ratios 等价。读 `blastgame-multi-tier-designer` skill 或 `references/probe-design.md`，不自己脑补。
   **不要随意换 sc！** sc 切换只在参数断层（如特定 WR 区间无可行配置）时考虑，不是常规调参手段。如果没有明确的断层参考点就动 sc，会被纠正。
10. **删文件前查 skill 引用。** 特别是 `project-state/` 和 `tools/` 下的文件，可能被 skill 的流程/命令引用。先 `grep "文件名" skills/*/SKILL.md` 确认无引用再删。
11. 不重复发明轮子，融入现有 skill。新增检查/规则时优先扩展现有流程（加一步/加一条）而非另起炉灶。用户明确说过不要光做加法，要注重与现有的skill融合。
12. 不猜根因、不打临时补丁。发现异常数据时先完整展示数据对比定位问题。根因确认前不拍脑袋加 workaround（如互换 asset 索引）。每次猜测性修复都在浪费批跑时间，用户会批评。
13. **改关卡判断只用当前最优配置的死亡分布。** 探针数据是实验性质的——故意用非最优参数测试空间，其死亡分布不反映关卡真实难度。改关卡预判公式 `earlyDeath > (1-targetWR)×80%` 只对 `find_best_combo` 的 `#1 combo` 生效。
14. **Normal 模式也跑满 5 档。** 固定 `--tiers "1,2,3,4,5"`。T1=T2、T4=T5 同难度但配置不同，等于白送 2 个额外探针槽，每轮多 66% 数据。
15. **Phase2 CSV 列偏移。** C# 导出 Phase2Appended 列不输出导致数据列比表头少 1 列时自动检测：比较数据行和表头的列数，少则左移解读（Phase2Appended→sd, StartDifficulty→sc, ShuffleSplitCount→ratios, ShuffleSplitRatios→of）。不依赖任何字段的值内容。
16. **改关卡旧数据清理。** 不删 BlastGame 目录下任何文件。在 `_last_refresh.json` 的 `asset_updated_at[lv]` 写当前时间戳，pool 刷新时自动跳过该时间前所有数据（bot 批跑 + optimizer 数据）。
17. **状态变了立即更新 board.md。** 改关卡→待调优、待调优→入库等状态变化时，第一时间更新 `project-state/board.md` 和 `timeline.md`，不等"等会有空再...[truncated]

---

## 诊断流程（异常数据时执行）

看到"空 CSV"、"全 100%"、"全 0%"、"死区"时，按顺序排查，不跳步：

```bash
# ① 数据源全貌（不看 bot400 就下定论）
python -c "from tools.data import pool; recs=pool.dedup_records(pool.get_preferred_records(str(LV))); print(f'bot={sum(1 for r in recs if r.get(\"source\")==\"bot\")} sum={sum(1 for r in recs if r.get(\"source\")==\"summary\")} phase={sum(1 for r in recs if r.get(\"source\") in (\"phase2\",\"phase1\"))}')"

# ② Asset 格式三板斧
grep "m_Name:" {asset}                           # 必须=关卡号
grep "customCellDrawingListV2:" {asset} | head -1 # 缩进不能=0
grep "difficultyLevel:" {asset}                   # 0/1/2
python -c "from tools.asset_patcher import read_ddc; print(len(read_ddc(LV)))"  # 必须=5

# ④ 如果 tier 映射疑似异常（T1 配置与预期不符）
# 根因已确认：AssetDatabase 缓存过期。修复见 references/tier-mapping-debug.md「根因确认与修复」。
# 排查步骤仍保留如下（当修复后仍然复现时使用）：
# 渐进式 Debug.Log 追踪（从上层到下层，每轮加1-2层）：\n#   第1层: RunBotBatchByLevelRangeForJenkins 循环 → [BatchDebug] Processing tierIndex/forcedTier\n#   第2层: request 创建处 → [BatchDebug] Created request hash/ft\n#   第3层: BlastBotBatchRunner.Run 入口 → [BatchDebug] Run(hash=...)\n#   第4层: BuildAttemptResult → [BatchAttemptDebug] requestHash/reqFT/appliedTier/sd\n#   第5层: ResolveTierDifficultyConfig → [TierDebug] tier/resolvedTier/tierIndex/sd + configs[0-4]\n#   第6层: BlastDifficultyContextFactory.* → [CtxDebug] forcedTier/sd\n# 先在 submit_batch_unity.py 加过滤条件。见 references/tier-mapping-debug.md\n\n# ③ batch mode 空 CSV → batch-mode-troubleshooting.md
```

**绕过的步骤一定会回来打脸。** 本会话中多个错误都是跳过了第①步（直接看 bot400 下结论）和第②步（直接怪 bot 太强/license 问题）。

---

## 三批流程

```
批A 决策 → 批B 执行 → 批C 裁定
```

### 批A — 决策
1. `preflight.py submit --levels LV --tiers T`（asset 5档、sc/ratios匹配、--tiers非空、board冲突、Editor冲突）
2. 检索池子 → `find_best_combo` → 逐条过 judgment-rules.md
3. 设计探针 → 写入 `probe_configs.json`

### 批B — 执行（Bot 运行期间的空闲时间利用）

**重要：tier 映射问题已确认根因：**submit_batch_unity.py 的 preflight 会用 probe_configs.json 覆盖 asset，导致手动修改的配置被冲掉。** 排查写入问题时先确认 probe_configs.json 的值。

```bash
# 提交
python scripts/submit_batch_unity.py "82,98" --games 400 --tiers 1,2,3,4,5

# 注意：提交前确保 Unity Editor 已关闭。Unity batch mode 需要独占工程锁，Editor 开着会报
#   "another Unity instance is running with this project open"
# 如果持续报该错误：① `taskkill //F //IM "Unity.exe"` ② `rm -f "$BLASTGAME_REPO/Temp/UnityLockfile"`
# 排查配置不符时先检查 probe_configs.json 的值是否与预期一致
```

提交后 Unity 开始批跑，约 30-60 分钟。这段时间可以做有限、有明确产出的事：

**必做（3-5 分钟）：**
1. **快速复盘上一轮** — 如果刚跑过一轮且出了结果但还没分析：
   - 看 `post_batch_review.py` 或 `find_best_combo` 的输出有没有异常（空数据、全 100%、全 0%）
   - 有异常则标记（写到 `wrongbook.md` 或 记下来等 bot 跑完再处理）
   - 无异常则不需要深入分析——等这轮跑完一起看
2. **检查 board.md 状态是否过期** — 如果状态变了（改关卡→待调优等），更新一下，3 秒的事
3. **更新 timeline.md** — 记录提交事件，10 秒的事

**按需做（10-15 分钟）：**
- 如果上一轮发现了明确的 bug（如 asset 写入错误、脚本报错、tier 映射异常），在 bot 跑的时候排查代码，而不是等跑完再查
- 如果已知下一轮要做什么（如下一轮探针方向已经定了），提前写好 probe_configs，等数据一出来就能直接提交

**不做的事：**
- ❌ 搜网页找灵感（大概率不相关，token 白花）
- ❌ 大规模重构代码（容易半途而废）
- ❌ 分析还没出的数据（纯空转）
- ❌ 在根因未确认前打临时补丁（如互换 asset 索引的猜测性修复）

**原则：** 跑 bot 期间只解决"不跑 bot 就解决不了"的问题（如 bug 排查），不做"任何时候都能做"的低价值优化。

### 批C — 裁定
1. `python tools/post_batch_review.py --batch {batch_dir} --full`（批后自动分析：展示新数据 vs 之前 best 的 WR/死亡分布变化，并逐档检查 probe configs 是否与预期一致）
2. 如果无 batch 参数则自动使用最新 batch: `python tools/post_batch_review.py --full`
3. `dump_level_pools` → `find_best_combo --top 3`
4. 逐条过 judgment-rules.md（①数据源 → ②合格判定 → ③硬性违规 → ④档差审美 → ⑤结果分级）
5. 死亡分布分析：查看最佳组合 T1 的 earlyDeath（桶 0-1 和），算阈值 = (1 - 目标WR) × 80%。如果 earlyDeath > 阈值 → 标记改关卡
6. 标记 ✅合格 / ⚠️接近 / ❌不合格

---

## 协操 — 按需调用模块

### 数据检索
```bash
python tools/find_best_combo.py {lv} --top 3
```
数据来源优先级（完整表见 `references/pool-priority.md`）：
```
0: bot≥400  1: summary≥400  5: bot300-399  10: bot200-299  15: bot<200
```
`dedup_records` 自动去重，传全部 `recs` 给 `find_best_monotonic`，**不预过滤数据源**。

### 探针设计（加载 `probe-design.md`）

### 判定
```bash
python tools/judge_level.py {lv}
python tools/find_best_combo.py {lv} --top 3
```

### 入库（绝不自动）
1. `write_ddc(lv, tiers)` → asset
2. `write_excel.py` 写入（自动展开 Normal，写后校验 T1-T5 非空）
3. 更新 board.md、timeline.md
4. 备份 asset 到 `asset_backups/snapshot-{date}/`
5. `postcheck.py 入库 {lv}` 验证

### 改关卡
```bash
python tools/retire_level.py 59 --reason "T1 ceiling"
```

**改关卡后必须立即做：**
1. 清除池子数据：`rm -rf stage-data/{lv}`
2. 从 `_summary.json` 移除此关卡
3. 清理旧 bot 批跑数据：`find "$REPO/telemetry/bot/" -maxdepth 1 -name "*{lv}*" -not -path "*{lv}-{lv}*" | xargs rm -rf`
   — 旧批跑目录中的该关卡数据会让池子在重建时优先选老数据（更高 WR），而不是 redesign 后的新数据
4. 清理 UnityLockfile：`rm -f "$REPO/Temp/UnityLockfile"` — 如果 Editor 崩溃残留锁文件，后续 batch mode 启动会报 "another Unity instance is running"。锁文件无进程持有时可手动删除。
5. 更新 `timeline.md` 记录改关卡原因
6. 更新 `board.md` 状态
7. 旧数据已作废——后面等 redesign 后的新数据重新导入并验证

**redesign 数据导入后验证：**
- `dump_level_pools` 重建池子后，立刻 `find_best_combo {lv}` 确认显示的是新数据（sd/ratios 符合 redesign 配置）
- 如果池子仍显示老数据（高 WR）→ 检查 `telemetry/bot/` 是否还有旧批跑目录残留

状态自动恢复：`preflight.py check-retired` → 有组合 → 移回待调优。

**等待外部数据时的原则：**
当你在等改关卡数据、等批跑结果、等用户提供信息时，不要干坐着。主动做现阶段能做的准备：
- ✅ 清除过期数据（改关卡后清池子）
- ✅ 更新文档/记录（timeline/board）
- ✅ 准备下一轮探针方案（提前写 probe_configs）
- ✅ 排查已发现的 bug（如 tier 映射）
- ❌ 不要等用户说"做下一步"才动——自己判断什么能提前做

---

## 工具链

| `preflight.py` | 提交前验证（asset/board/Editor/unit-only）。`submit` 含 `check_asset_readback`（信息级对比 probe_configs，不阻止）|
| `postcheck.py` | 入库/改关卡后自检 |
| `write_excel.py` | Excel 写入（展开 Normal，验证 T1-T5）|
| `retire_level.py` | 改关卡归档 |
| `asset_patcher.py` | 写 asset（v5.3+ 自动修 ccV2 缩进）|
| `dump_level_pools.py` | 刷新池子 |
| `find_best_combo.py` | 最佳组合搜索（支持死亡分布 + 改关卡预判 + 调参方向提示）|
| `post_batch_review.py` | 批后自动分析（读批次 CSV，对比 probe_configs 检测偏差，对比池子展示 WR 变化）|
| `submit_batch_unity.py` | batch mode 提交（主） |

---

## 设计参考

| 文档 | 说明 |
|------|------|
| `references/pre-task-checklist.md` | **动手前检查清单** — 每次任务前过一遍，防漏skill/防参数错/防缺口评估错 |
| `references/probe-design.md` | 探针设计、缺口评估、槽位分配、参数设计 |
| `references/param-nonlinearity.md` | 四参数非线性参考：of/sd/sc/ratios 实测数据 + 16组预设 |
| skill:blastgame-judgment | **独立 skill** — 判定规则（数据源/合格/硬性违规/审美/分级）。裁定时加载此 skill |
| `references/pool-priority.md` | 数据来源优先级（bot/summary/phase）|
| `references/asset-format-debug.md` | asset YAML 格式调试、m_Name、difficultyLevel |
| `references/batch-mode-troubleshooting.md` | 空 CSV/秒杀/不启动 排查流程 |
| `references/tier-mapping-debug.md` | Tier 映射调试 — 排查步骤与日志方法（asset 回读正确但 Unity 读错时的排查流程） |
| `references/post-batch-review.md` | 批后自动分析工具使用参考 |
| `references/game-mechanics-overview.md` | 游戏玩法机制概述 — 不理解游戏是炮台自动射击而非手动瞄准时，先读本文 |
| `references/failbucket-mapping.md` | failBucketDistribution 死亡分布参数映射 — 桶阶段定义、改关卡公式、调参方向参考 |

---

## 常用命令速查

```bash
# 三段验证（每次必做）
python tools/preflight.py submit --levels LV --tiers T
python tools/postcheck.py 入库 LV
python tools/preflight.py check-retired

# 关键诊断命令
python -c "from tools.asset_patcher import read_ddc; cfg=read_ddc(LV); print(len(cfg))"  # 5档
python -c "from tools.data import pool; print(len(pool.dedup_records(pool.get_preferred_records(str(LV)))))"  # 全量数据

# 提交
python scripts/submit_batch_unity.py "56,57,71" --games 400 --tiers 1,2,3,4,5
python tools/find_best_combo.py 56 --top 3
python tools/dump_level_pools.py
```

---

## 易犯错误速查

| # | 错误 | 防护 |
|---|------|------|
| 1 | 只看 bot400 就下定论（忽略 summary/phase2） | 查 `len(recs)` 看全量 |
| 2 | 探针和验证混在一起提交 | 验证用 `--skip-patch --tiers 1,3,5` |
| 3 | 修 asset 用其他关做模板整体替换 | 只改 tiers 段，不动 m_Name/牌面 |
| 4 | 压缩进 5 槽不利用 Normal 空槽 | T2/T5 空槽放辅助配置 |
| 5 | Hard/SuperHard 5 槽平均分配 | 集中打缺口方向 |
| 6 | 预过滤数据源后找组合 | 传全部 `recs` |
| 7 | 用户确认探针方案后手动拆check_unity/restart_unity | submit_batch.py / submit_batch_unity.py 内部处理 Unity，不手动拆步骤 |
| 8 | 改名后漏查文件引用 | rename 后用 `rg "旧名字" D:/path/ --glob '!_archive/**'` 搜全部非归档源文件 |
| 9 | `find_best_monotonic` 参数顺序传错 | 签名 `(records, targets, top_n=1, difficulty='hard')` — `difficulty` 是 keyword 参数，不要当位置参数填。正确：`find_best_monotonic(recs, targets, difficulty='normal')` |
| 10 | gap 评估时目标值多除了 100 | bot WR 和目标都是**百分比**（如 81.25 vs 90），直接比。`t = tiers[idx]` 不是 `tiers[idx]/100` |
| 11 | 设计探针前没读 probe-design.md | 探针设计必须加载 `references/probe-design.md`。参数理解（of非线性/sc含义/sd非单调）全在里面 |
| 12 | 不知道 Hermes 有 skill 可用 | 任何时候先 `skills_list` 查看可用 skill，再 `skill_view(name)` 加载。skill 在 `~/AppData/Local/hermes/skills/` 下，不在项目文件夹里 |
| 13 | `search_files` 用 MSYS2 路径 `/d/` 报错 | 该工具底层是 Windows 原生 ripgrep，必须传 `D:/` 格式路径。见 `blastgame-bot-orchestrator` 的 `references/tool-path-format.md` |
| 14 | `preflight.py` 解析 board.md 的 pending 关键词不匹配 | board.md 用的是「待调优」，同步更新 preflight.py 的 get_board_levels() 关键词 |
| 15 | 把死亡分布当改关卡唯一依据 | 初始牌面死亡 > (1-目标WR)×80% 是预判条件之一，但不是唯一。还需结合 span 预判、6 轮上限、硬性违规综合判定 |
| 16 | sd=0 和 of=0.01 不同时试 | 探 WR 上限时两个参数可同时压极值（sd=0 + of=0.01），这是探边界不是精调 |
| 17 | **SuperHard 下 sd 反直觉** | Normal 下调低 sd 通常会提高 WR（更容易），但 **SuperHard (difficultyLevel=2) 下调低 sd 反而可能降低 WR**。原因是难度底板由 difficultyLevel 决定，sd 增量的非线性在 SuperHard 下表现不同。经验：L98 的 T5，sd=5→6.0%、sd=8→7.0%、sd=10→0.5%，峰值在 sd=8。调 SuperHard 关卡时，**sd 不要太低也不要太高**，从最优附近小步调整。 |
| 17 | wrongbook.md 和 skill 内容重复 | Doc/wrongbook.md 只放流程级错误，参数知识放 skill |
| 18 | **tier 映射 bug** — 多轮提交 T1 读到的配置与 T4/T5 相同。**根因已确认：Unity AssetDatabase 缓存过期。** Python 写 asset 后 Unity 的旧二进制缓存使 DynamicDifficultyConfigs 读取错序。**修复：** `BlastBotJenkinsBatchEntry.RunFromCommandLine` 加 `AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate)`。详见 `references/tier-mapping-debug.md`。 | 任何重现 tier 错位时，查 `AssetDatabase.Refresh()` 是否在 asset 加载前执行 |
| 19 | **`funnel_b/` 也有同名 asset** | 每关 `.asset` 在 `test/` 和 `funnel_b/` 各有一份。`funnel_b` 是默认分组，`test` 是 batch mode 实际使用组。两文件可能版本不同（`diff` 确认）。排查异常时先 `find "$REPO" -name "{lv}.asset" | grep -v ".meta"` 确认重复，再 `diff test/{lv}.asset funnel_b/{lv}.asset`。Python 工具只读写 `test/`，但 Unity 若加载到 `funnel_b/` 版本会导致配置混乱。 |
