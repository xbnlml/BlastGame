# 2026-08-04：关卡数据库写入 + board 重写 + Excel 位置事故

## 1. 贝叶斯停止参数化（坑 85/91/94）

**问题**：`submit_batch_unity.py` 硬编码 `-BlastBotBatchAdaptiveStop 'true'`，用户手动验证 400 局时只跑了 250-300 局（early:threshold 提前停）。用户暴怒："就不能通过输指令吗，每次都要改这个地方才能控制贝叶斯？"

**修复**：
```python
parser.add_argument('--adaptive-stop', action='store_true',
                    help='开启贝叶斯自适应提前停止（默认关闭=跑满局数）')
...
'-BlastBotBatchAdaptiveStop', 'true' if args.adaptive_stop else 'false',
```

**铁则**：行为开关必须做成 CLI 参数（`parser.add_argument('--xxx', action='store_true')` + 条件传值），不允许改常量/注释开关。

**验证**：手动跑 400 局用默认参数（不带 --adaptive-stop），跑完检查 campaign-summary CSV `winCount + failCount == 400`。多档位优化器 summary 里的 WR 可能是提前停的（如 L197 T5 250 局 early:threshold），bot 验证前先看 TotalRuns。

**命令注意**：`submit_batch_unity.py` 的 levels 是**位置参数**（`python scripts/submit_batch_unity.py 197 --tiers 5 --games 400`），不是 `--levels 197`。

## 2. 关卡数据库 11 关写入（LevelDatabase/Run/test.json）

**流程**（已验证，`hermes/tools/leveldb_sync/`）：
1. python 脚本：从池子按 asset 配置（config_key 四元组）匹配同配置 verified 记录 → 生成 `_write_payload.json`（含 tierWinRates + failBucketDistribution）
2. `node write_level_db_dryrun.mjs` — 内存验证（loadRunStore + upsertRunEntry + resolveActiveRun），不写盘
3. 用户确认影响范围（写前说明会变/不变的文件）
4. `node write_level_db.mjs` — 写前备份 `Backups/pre_hermes_write_*.json` → upsertRunEntry → saveRunStore（官方自动备份+原子写+稳定排序）→ 回读验证

**写入明细（2026-08-04）**：L158/159/163/168/172/174/175/184/186/194/197，全部 `sourceFileName=hermes-import-20260804.csv`，回读验证 11/11 通过，旧 entry 全保留（entries 数 2-4）。

**关键**：entry 9 字段与官方全等（fingerprint/tierConfigs/tierWinRates/tierFailDistribution/perTierMeta/importedAt/sourceFileName/sourceFormat/lastResolvedAt）；tierFailDistribution 用池子补的官方 10 段串；fingerprint 从 asset 算（sha256 前 16 hex）。

**只读对比脚本**：`tools/compare_level_db.py`（输出 DB 活动 entry vs 池子同配置 WR 对比表）。

## 3. board.md 每关一行重写（坑 99）

**用户要求**："board.md是怎么记录的？不应该是每关单独计吗？然后后续每关只在对应关的地方更新"

**新格式**：表格每关一行 `| 关 | 难度 | 状态 | 入库日期 | 目标 | 最优档位 WR% | 备注 |`，状态变更只改对应行。

**重写脚本**：`project-state/rewrite_board.py`（幂等，可重复跑）：
- 状态硬编码（imported/pending/redesign 三个列表），不从旧格式解析（旧格式解析会把待调优从 11 变 4）
- 已入库关的最优 WR 从 Excel 最新组读（不查池子——池子 dedup 可能埋入库版本）
- Excel 分组：备注为空 = 旧记录组；备注非空 = 新记录组（备注逐行不同也合并为一组，如 L153 phase0 260/360/370 局）

**旧格式问题**：三个大列表追加式 → 关卡号重复（153/168/186/188 出现两次）、状态变更要跨列表移动容易漏（L153 已入库但需改关卡没删）。

## 4. Excel 位置事故（坑 98，严重）

**事故**：入库记录 Excel 误写 `<BLASTGAME_REPO>\Doc\手动挑配置记录.xlsx`（BlastGame 项目里），正确位置是 `<HERMES_ROOT>\手动挑配置记录.xlsx`（hermes 工作区）。用户暴怒："让你写的excel是BlastGame里的excel？？？？？？？？？？？？？？？？？？？？？？？"

**根因**：memory 里"手动挑配置记录.xlsx"没写路径，之前会话一直用 BlastGame Doc 的路径，惯性延续。

**修复**：
1. 备份 hermes 原版 → `手动挑配置记录_hermes原版_20260804.bak`
2. 把 BlastGame 版完整复制到 hermes 版（用户历史 + 我们的入库记录都在）
3. 用户用 SourceTree 还原 BlastGame 里的

**铁则**：BlastGame 项目目录（`<BLASTGAME_REPO>/`）内任何文件禁止写。写入前确认路径前缀是 `<HERMES_ROOT>\`。

## 5. 池子 dedup 埋新批次数据（坑 89/96/100）

**案例**：L155 T1 配置 sd=6,sc=6,ratios=0,1,0,1,0,1,of=0 有 phase0 37.3%（370局）vs summary 83.3%（240局）差 46pp，dedup 按局数分档保留 370 局的，新批次被埋。

**排查链**：池子看不到 → 查 `LevelDatabase/Run/test.json`（按 fingerprint 保留全部历史）→ 查 `telemetry/multi-tier-opt/*/summary.csv` 的 SourcePhase + VerifiedWinRate → 确认数据有效 → bot 400 局验证真实值。
