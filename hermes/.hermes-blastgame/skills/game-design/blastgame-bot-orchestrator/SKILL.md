---
name: blastgame-bot-orchestrator
description: "BlastGame Bot 批跑 — batch mode(唯一), 5档目录轮询监控、配置验证(sc/ratios)、故障恢复"
version: 6.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
category: game-design
metadata:
  hermes:
    tags: [blastgame, game-design, bot, batch, monitoring, unity]
---

# BlastGame Bot 批跑

> **被 `blastgame-level-optimizer` 调用。**

## 0. 核心规则

- **先展示结果再问下一步。** 执行完操作后必须展示数据（表格优先），不跳到"继续？"。
- **禁止主动启动 Unity 编辑器。** batch mode 不需要编辑器。
- **batch mode（`submit_batch_unity.py`）是唯一提交方式。** 旧 editor trigger (`submit_batch.py`) 已废弃，文件已删除。
- **`--tiers` 必填，无默认值。**

### 诊断优先
发现异常数据时，先展示完整的逐关逐档逐参数对比，定位根因，再提修复方案。**不要自己猜原因直接动手修。**

## 1. Batch Mode 提交（唯一方式）

**工具：** `D:/download/Hermes/scripts/submit_batch_unity.py`

```bash
python "D:/download/Hermes/scripts/submit_batch_unity.py" "89,90,91" --games 400 --tiers "1,2,3,4,5"
```

**提交前运行 `preflight.py` 验证：**
```bash
python D:/download/Hermes/tools/preflight.py submit --levels 89,90,91 --tiers 1,2,3,4,5
```

**原理（使用 Jenkins 官方入口 `BlastBotJenkinsBatchEntry.RunFromCommandLine`）：**
```bash
Unity.exe -batchMode -nographics -projectPath "..."
  -executeMethod BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine
  -BlastBotBatchLevels "89,90,91" -BlastBotBatchRunCount 400 -BlastBotBatchTiers "1,2,3,4,5"
  -logFile - -quit
```
Python patch .asset → 拼命令 → Unity headless 进程 → 自动编译+import 外部修改的 .asset → 跑 bot → 退出。
`-logFile -` 实时输出进度（可见 `[Bot Batch Jenkins] 完成`）。

**关键优势：**
- 不依赖 Editor trigger，无 NRE 崩溃，无 `_isRunning` 锁死
- 每次全新进程，无"批次间触发死掉"问题
- 自动 ImportAsset 刷新外部修改的 .asset

---

> ~~Editor Trigger 提交 (`submit_batch.py`) 已废弃，文件已删除。~~ 历史参考见 `references/submission-methods.md`。

## 1b. 注意事项

- `submit_batch_unity.py` 已支持 `--dry-run`（验证配置和 asset 完整性，不实际运行 Unity）。提交前仍建议用 `preflight.py submit` 做前置验证。
- **提交前必须加载 skill**：`skill_view(name="blastgame-level-optimizer")` + `skill_view(name="blastgame-bot-orchestrator")`。技能在 Hermes 系统目录 `~/AppData/Local/hermes/skills/` 下，不在项目文件夹里。用 `skills_list` 查找可用 skill。

---

## 2. 完成检测

| 阶段 | request.json | bot 目录 CSV | 含义 |
|------|-------------|-------------|------|
| 提交后 | 存在 | 不存在 | 未拾取 |
| 运行中 | 存在 | 部分 tier 有 CSV | 正在跑 |
| 完成 | 不存在 | **5 个 tier 全有 CSV** | 跑完了 |

**不要等 `auto-batch-result.json`。** 用 bot 目录 T1-T5 + CSV。

**监控工具：** `python D:/download/Hermes/tools/monitor_bot.py "81" --tiers "1,2,3,4,5" --timeout 7200`

---

## 3. 验证工具

### 提交前验证
```bash
python D:/download/Hermes/tools/preflight.py submit --levels 59,81,82 --tiers 1,2,3,4,5
python D:/download/Hermes/tools/preflight.py asset --levels 59,81,82
```
检查项：asset 5 档纯净、sc/ratios 匹配、`--tiers` 非空、board 已入库/改关卡冲突、Unity 编辑器进程冲突。  
`check_asset_readback` 对比当前 asset 与 probe_configs（仅信息级提示，不阻止提交）。

### 提交后回读验证（防写入错误）
`submit_batch_unity.py` 在 `write_ddc` 写 asset 后立即调用 `read_ddc` 回读，逐字段对比 `probe_configs`。不一致则终止提交，防止因 Python 脚本错误导致 asset 写入异常白跑一轮 bot。

### 批后分析（新批次结果对比池子）
```bash
python D:/download/Hermes/tools/post_batch_review.py           # 最新 batch
python D:/download/Hermes/tools/post_batch_review.py --batch "82_98-..."  # 指定 batch
python D:/download/Hermes/tools/post_batch_review.py 59,81 --full  # 带死亡分布
```
自动读取批次 CSV、对比 `probe_configs` 检测配置偏差（可发现 tier 映射问题）、对比池子最佳展示 WR 变化。

### 操作后自检
```bash
python D:/download/Hermes/tools/postcheck.py 入库 62
python D:/download/Hermes/tools/postcheck.py 改关卡 59
```
检查项：Excel T1-T5 非空、Normal 结构正确、asset vs Excel 一致、snapshot 备份、board 总数。

### Excel 写入（替代内联代码）
```bash
python -c "from tools.write_excel import write_tiers; write_tiers(LV, tiers)"
```
自动展开 Normal 关 T2=T1、T5=T4，写入后逐行验证 T1-T5 非空。

### 运行后验证

从 campaign-attempts.csv 第一行读 startDifficulty，比对 asset 的 sd 值。不等则跑了旧配置。

---

## 4. 排错

### Asset 格式问题

| 现象 | 排查 |
|------|------|
| 全 100% WR、board 读不到、clearedCellCount=0 | **indent 错误：`customCellDrawingListV2:` 缩进为 0（应为与 `DynamicDifficultyConfigs:` 同级）**。当 `write_ddc` 写入替换 tiers 后，`customCellDrawingListV2:` 可能保持 0 空格缩进（来自之前某次写坏的残留）。Unity YAML 解析到错误缩进 → `myStage`（牌面）和 `customCellDrawingListV2` 的父子关系断裂 → board 配置无效 → bot 跑 0 clearedCellCount 的假游戏。检测：`grep -n "customCellDrawingListV2:" *.asset`，第一个应在行首有至少 4 空格。修复：`sed -i '0,/customCellDrawingListV2:/s/^customCellDrawingListV2:/    customCellDrawingListV2:/' *.asset` |
| bot 跑关 51 或其他默认关 | **`m_Name` 错误**：Unity ScriptableObject 的 `m_Name` 字段是关卡身份 ID。用其他关的 asset 做模板重建时，`m_Name` 仍未改 → Unity 认为 asset 是模板关。检测：`grep "m_Name:" *.asset`，应等于关卡号。修复：改 `m_Name: N` 为实际关卡号 |
| 用模板重建后关卡参数丢失（棋盘/牌面） | **不要用 template 整体替换**。每关的 `myStack`（棋盘尺寸、池值）、`myStage`（牌面绘制配置）等参数是独有的。必须从该关自身备份（`.asset.bak` 或 git）恢复原文件，再只替换 `DynamicDifficultyConfigs:` 到 `customCellDrawingListV2:` 之间的 tiers 段 |

### C# Debug.Log 调试要点（2026-07-18 实战教训）

向 Unity C# 代码加 `Debug.Log` 调试时：

1. **一次只改一个文件，加最少量的 log。** 改动多文件时如果某个文件编译失败，Unity 会**静默回退到旧 DLL**，导致**所有修改（包括已编译通过的）全部失效**。
2. **验证编译成功：** Unity 启动日志中查找 `LogAssemblyErrors (0ms)`。不出现该行 = 无编译错误。如果报 compile error，所有 debug log 都发不出来。
3. **修改后提交一次跑一批。** 不要连续改多个文件再跑——如果中间某个改动引入编译错误，之前所有改动都看不到效果。
4. **不要在 patch 中改返回类型或访问修饰符（`public`↔`internal`）。** 即使改回原值，也可能引起编译器找不到类型的间歇性错误。
5. **确保 Python 端 filter 包含你的 log tag。** `submit_batch_unity.py` 的过滤逻辑需要更新。
6. **如果 log 不出现但编译成功：** 检查 `-logFile -` 是否在 cmd 中、subprocess 的 pipe 是否被行缓冲。batch mode 的 `-logfile -` 已确保实时输出到 stdout。
7. **无用 log 要清理。** 问题确认后立即 `git checkout` 恢复改过 log 的文件，或反向 patch 删除 log。积压的 log 会干扰后续排查（以为自己加了新 log，实际是老 DLL 还在跑）。

### 运行时问题

| 现象 | 排查 |
|------|------|
| shuffleSplitRatios mismatch | ratios 逗号数 ≠ sc 值 |
| 跑了旧配置 | `--skip-patch` → asset 不更新 |
| Unity 退出码 1 但数据已产出 | 正常。NRE 发生在 `window.Close()`，bot 数据已写 |
| CSV 空（仅表头） | 检查 CSV 数据行：若 winCount=400×关数（如 2400=6×400）、level 为 51（默认关）→ 新 bot 分支的导出逻辑将多关合并为 1 行 |
| asset 读出 >5 档 | `write_ddc` 重复调用 → 文件末尾累积。从 git 或 `.asset.bak` 恢复原文件，用 `write_ddc()` 覆盖 |
| result.json 不存在 | 查看 bot 目录 T1-T5 → 刷池子 |
| **Tier 映射错位**：T1 配置实际在 T5 档跑 | **⚠️ 根因未确认，禁止打临时补丁。** asset 写入正确（`read_ddc` 返回 5 档参数正常），C# `ResolveTierDifficultyConfig` 代码逻辑也正确（`tierIndex = resolvedTier - 1`），但 bot 实际运行时 T1 多次出现读取最末档参数的情况。\n\n**已排除的根因：**\n1. ~~C# 索引计算~~ — `tierIndex = resolvedTier - 1` 逻辑正确，`configs[0]` 加载后打印也正确\n2. ~~dedup 机制~~ — 2026-07-18 实测关闭 `-BlastBotBatchDedupeEnabled false` 后问题依旧\n\n**当前排查状态（2026-07-18）：**\n- `ResolveTierDifficultyConfig` 加日志后发现只收到了 tier=5 的多次调用，未见 tier=1~4 的调用\n- batch 模式走的是 `BlastBotBatchRunner`（不是 `BlastBotCampaignRunner`），批量创建尝试时 `request.forcedTier` 始终为 5\n- `funnel_b/` 下的原始 asset 中所有 5 档配置完全相同（sd、sc、ratios、of 均相同），可能埋下了序列化处理时的隐患\n- Python asset_patcher 写入 YAML 格式正确，但 Unity 反序列化时可能因 YAML 列表排序机制不同导致索引偏移\n\n**排查方向：**<br>(1) 在 `BlastWorkbenchWindow.Bot.cs` 的 tier 循环入口（`forcedTiers` 迭代处）加 log，确认每个 tier 实际收到的 `forcedTier` 值<br>(2) 检查 `BuildBotBatchDedupeKey` 是否因有效配置相同导致 T1~T5 的 dedup key 碰撞（`funnel_b` 所有档参数相同可能影响 Key 计算）<br>(3) 测试只用单档（`--tiers 1`）提交，排除多档相互干扰<br>(4) 对比 `funnel_b/` 和 `test/` 两套 asset 在同一次批跑中的行为差异 |

### `write_ddc` 写入后自动修正缩进
`asset_patcher.py` v6+ 在写入后自动检测并修正 `customCellDrawingListV2:` 的缩进。如果它出现在行首（0 空格），会自动补上缩进。此修复在 `write_ddc()` 函数的验证步骤之前执行。
