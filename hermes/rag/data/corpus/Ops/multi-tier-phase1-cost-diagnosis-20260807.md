# 多档位 phase1 耗时排查 + 候选冗余分析（2026-08-07）

## 背景
用户反馈"跑一关多档位优化比以前慢很多"，要求查原因。教训：**不能凭记忆猜旧机制，必须对比新旧代码/历史批次数据**（用户原话："你根本没了解以前的机制，你好好看看"、"以前怎么可能phase1只跑16个候选呢？"）。

## 排查方法论（已验证，按此顺序）

1. **对比新旧代码**：`git diff` 只读查看改动（用户明确要求查新旧差距时允许执行 git diff——SourceTree 用户自己也能看）。本次 diff 显示 Sampler +130 行 / Optimizer +82 行。
2. **对比历史批次 manifest**：所有批次目录 `telemetry/multi-tier-opt/*/run_manifest.json` 的 `Phase1Samples`/`Phase1Runs`/`Phase2Runs` 等参数。本次发现新旧参数完全一样（Phase1Samples=100 都是默认值），**参数没变，是代码逻辑变了**。
3. **对比 phase1_raw 行数**（候选数）：
   - 8-06（改前最后批次）L110：**32 候选**
   - 8-03（旧机制全量）L110：71 候选（28 mandatory + 40 extension + 2 fill + 1 baseline）
   - 当前（改后）：90+ 候选（R1a 75 + R1b/R2 15）
4. **看 Unity 日志进度**：`Editor.log` 里 `[MultiTierOpt] Cumulative N runs completed, ... phase=Phase 1 Round 1: sample x/100` 可看到当前跑到第几个候选、累计局数。
5. **计算每候选耗时**：批次开始时间 → 当前时间 → 累计局数 → 每 100 局秒数。

## 根因结论

**phase1 候选数 32 → 99 是变慢直接原因**（3 倍），源于 R1a 重设计：
- 旧：`BuildRound1Plans` 锁 `Round1StartDifficulty=20`，`actualCount = Mathf.Clamp(count, 0, RatioPresets.Length)` → R1a 最多 16 候选，R1b/R2 按需补（8-06 只补到 32 就停）
- 新：`Round1TotalPresetCount = 5sd × 15ratios = 75`，R1a 直接吃满预算（`sampleSoftCap = phase1Samples = 100`），R1b 保 16 → 99 候选

**关键机制**：`sampleSoftCap`（=phase1Samples）是**软上限**，旧代码 R1b/R2 是"按需生成"（`CountSamplesInBand > 0` 就不补洞，计划生成完就停），跑不满 100 槽。新代码 R1a 全铺 75 直接占满。

## 批次时间戳陷阱（重要）

8-03 批次 25 关 manifest 全部同分钟（10:03）生成——**这是批启动时统一写入的假象，不代表并行**。skill 已确认 "Unity 不可并行"（multi-agent-workflow-20260730.md）。判断单关耗时必须看批次内各文件的 mtime 时间线（如 8-06 L110：18:30 manifest → 18:36 phase0 → 18:53 phase1_raw = phase1 17 分钟），不能看批启动时间。

## sd=0 与洗牌的关系（用户纠正过，别一刀切）

- `AllocateShuffleCounts`：`totalInt = numToShuffle = ceil(index/100 * size)`，`index = ComputeDifficultyIndex(ctx)` = `difficultyLevel × levelDifficultyFactor + loopOffset`（**由难度等级决定，不是 sd**）
- **normal 关 difficultyLevel=0 → index=0 → numToShuffle=0 → 完全不洗牌，ratios 无区分度**（实测 L110 sd=0 的 15 候选 wr 全挤 57~60%）
- **hard/superhard 关 difficultyLevel>0 → 即使 sd=0 也洗牌，ratios 有区分度** → **不能"sd=0 固定只跑一个"一刀切**
- 优化方向（未落地，待用户确认）：按难度区分裁剪——normal 关 sd=0 只跑 1 个代表候选；hard/superhard 保留全 ratios

## 优化候选冗余的思路（不降质量）

用户明确否定"phase1 局数 100→60"（=降质量，不是优化）。正确方向是**砍无信息量的候选**：
- 同 sd 下 ratios 无区分度（如 normal sd=0）→ 只跑代表候选
- 目标段已覆盖（CountSamplesInBand>0）→ 不补
- 借鉴旧机制"按需生成"：先跑骨架看覆盖，缺口再补，而不是全铺 75

## write_level_db.mjs 单档改造（2026-08-07 已落地）

- **DB 一直是单档 entry 结构**（1038 条全有 dealConfig，0 条五档组合 tierConfigs）——"五档组合 entry"是 write_level_db.mjs 旧版的错误设计
- leveldb 重构（12:08 同批 10 个 .mjs）：`tierConfigMatch.mjs` 从 `computeTierConfigFingerprint(tiers)`（五档）改为 `computeDealConfigFingerprint(tier)`（单档）；`runStore.upsertRunEntry` 要求 entry 有 `boardFingerprint`+`dealFingerprint` 否则返回 null
- 改造后 write_level_db.mjs：读 `_write_payload.json`（tierConfigs+tierWinRates 五档），逐档构造单档 entry（dealConfig + dealFingerprint + winRate + sourceTierLabels + boardFingerprint），boardFingerprint 从 asset 读（`readAssetSnapshot` → `data.boardFingerprint`，同关卡所有档相同）
- **normal 关 T1=T2/T4=T5 同配置 → 同 dealFingerprint → upsert 会 dedup 合并**，DB 只存一份（T1 匹配到 T2 的 entry），前端按配置匹配而非 label——验证脚本要按配置匹配（sd/sc/ratios/of 四元组），不是按 sourceTierLabels 数条目
- 验证：`hermes-verify-l136.py` 3/3（asset 配置=summary 入库配置、DB 按配置匹配正确胜率、5 档全绿）

## 通用教训

- **用户说"你好好看看以前的机制/代码"= 立即用 git diff / 历史批次数据对比，不许凭记忆**（本次被纠正 3 次才学会）
- **排查"以前快现在慢"：先排除参数差异（manifest 对比），再对比候选数（phase1_raw 行数），再看日志进度，最后看代码 diff 定位**
- **括号检查脚本必须正确处理单引号字符字面量（'\n' 等）**，否则误报 MISMATCH（多次踩坑）
