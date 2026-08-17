# bot400 全量批次审计 + 极端关判定（2026-08-11）

> 场景：51-200 全量 bot400 批次（telemetry/bot/51-200-2026-08-10T09-59-33）入池后做审美检查/极端关筛选/入库验证。
> 关联：`bot400-vs-db-consistency-20260810.md`（65% 不一致的首次发现）、`leveldb-single-tier-write-20260807.md`（DB 单档写入）。

## 1. bot400 全量批次结构（先认目录再对比）

- 位置：`telemetry/bot/<关卡范围>-<时间戳>/` 下每个档位一个子目录
  `L51-200-T1-<时间戳>-batch-range/campaign-summary-L51-200-T1.csv`
- summary CSV 字段：`level, Tier, BoardFingerprint, DealFingerprint, startDifficulty, shuffleSplitCount, shuffleSplitRatios, shuffleOverflowFactor, DifficultyLevel, winCount, failCount, winkate`
- **`winkate` 是小数（0.83 = 83%），读出来要 ×100**
- **批次目录可能被用户拷走/移走**（本次 51-200 批次跑完当天目录消失）——先 dump_level_pools 入池，对比改用池子 `source='bot'` 的数据，不要死等原始 CSV
- 每关每档一条 summary（750 条 = 150 关 × 5 档），同关同档只留最后一条

## 2. 同四元组对比法（bot400 vs 入库记录）

精确匹配键 = `(lv, sd, sc, ratios元组, of浮点)`，与 fingerprint 无关：
- DB 侧过滤 `identitySource == 'hermes-import'`（才是我们入库写的记录，bootstrap-current 是初始数据别混）
- 池子侧过滤 `source == 'bot'`
- 结果：73 条同参数匹配，37 条不一致（51%），偏差 ±20~48pp 双向都有
- 入库 summary/phase3 数据与 bot400 真机是两套机制，同配置能差 40pp——**同四元组 ≠ 同胜率**

## 3. write_level_db.mjs 两个坑（171/174 入库实证）

### 坑 A：payload 必须有 `tierWinRates` 字段
- `_write_payload.json` 每关需要 `tierConfigs` **和 `tierWinRates`**（小数 0.85 不是 85）
- 漏了 → `TypeError: Cannot read properties of undefined (reading '0')` at write_level_db.mjs:73

### 坑 B：normal 关回读验证报"部分验证失败（3/5 档）"是误报
- normal 关 T1=T2 / T4=T5 同配置，upsert 去重后只保留 3 个 entry（sourceTierLabels 只有 T2/T3/T5）
- 验证逻辑按"5 个独立标签"找 → normal 关永远 3/5
- **不是错误**：查 DB 确认 3 个 entry 的 winRate 覆盖全部 5 档（T1/T2 共用、T4/T5 共用）
- 最终确认用官方 `node tools/leveldb_sync/verify_packaging.mjs`（resolveActiveRun 全量 1000 档 + `tools/verify_asset_db_match.py --levels 171,174` 四元组↔DB 严格一致）

## 4. 审美标准检查法（51-200 全量筛）

两条标准，任一违反 = 不符合审美：
1. **单调递减**：T1≥T2≥…≥T5（相邻上升 >1pp 算倒挂；normal 允许 T1=T2/T4=T5）
2. **每档偏差 ≤15pp**（目标来自 `excel_target.get_target(lv)`——注意**返回 dict `{'diff':..., 'tiers':[...]}` 不是 list**，要取 `['tiers']`；值是小数 0.85 需 ×100）

## 5. 极端关分类（用户口径：只关心"过不去的"）

| 类别 | 阈值 | 影响 |
|---|---|---|
| 过不去（最严重）| 胜率 ≤5% | 玩家必败，直接流失——**用户只关心这个** |
| 太简单 | ≥97% | 用户明确"不影响游戏体验" |
| 相邻档跳变 | ≥30pp | 同上，不优先 |
| 严重倒挂 | ≥20pp | 同上，不优先 |

- **用户原话："主要是过不去的，其他的都不影响游戏体验"**
- 卡死档位分级：T1/T2 卡死（进关必败，最严重）> T3/T4 卡死 > 仅 T5 ≤5%（尚可接受但目标差太远）

## 6. 烂配置 = 孤儿配置（参数重叠分析法）

查"卡死档位参数和池子其他记录有无重叠"时：
- 完全重叠 = 池子里有同四元组记录——**但往往只有当天 bot400 刚写入的烂数据本身**（n=60-90），说明这是**孤儿配置**：asset 里一直放着、从没验证过、今天第一次跑就发现是烂的
- 同 sd 下有好配置（如 sd30 有 55.2%/36.0%，sd36 有 38.2%）→ **不是 sd 问题，是 ratios 组合选烂了**
- 结论：卡死档 = 替换成同 sd 已验证好 ratios 即可，不需要改关卡

## 7. 多档位批次失败模式：Phase1 T1 交叠门 0 候选

`96_106_163_171_174` 批次：96/106/163 failed，171/174 ok。
- 失败原因：`Phase1 档位 T1-超高胜率 交叠门内唯一候选仅 0 个（目标 80/85%，soft=8 absCap=15）`
- 含义：**T1 高胜率段（80-85%）数据不足**，优化器直接停，不跑后续
- 处理：先给 T1 段补数据/探针（打高胜率段），不能直接重跑
- 171（normal）救活案例：bot400 曾显示 T4/T5=0%，新批次找到 sd21/10,10,10,0,0 → 45.8%（差目标 4.2pp）✅

## 8. 入库工具链状态（2026-08-11）

- reimport.py 已明确输出"DB 同步失败（需手动 write_level_db.mjs）"——不再静默失败（P0 修复落地），但**第四动作仍要手动**：写 `_write_payload.json` → `node write_level_db.mjs` → 回读验证 → `verify_packaging.mjs` 全量确认
- write_ddc 写后 asset 回读验证 OK（171/174 各 5 档配置正确）

## 9. 51-100 全绿检查（用户口径：bot400 实测 vs 目标 ±10pp = 绿）

用户问"51-100 哪些关的新 bot 数据不满足全绿标准"——**这是纯检查任务，不扩展**（用户已连续纠正过范围）。做法：bot400 summary 每关每档 wr ×100 → `excel_target.get_target` 取 tiers → 每档偏差 ≤10 绿 / ≤15 黄 / >15 红。

结果（51-100 共 50 关）：
- **唯一全绿：L88**（71/54/41/10/4 vs 目标 70/55/40/25/15，仅 T4/T5 黄）
- **49 关非全绿**，两大模式：
  1. **T4/T5 过难**（20+ 关）：目标 50-60 实测 10-35（L66-100 大批 normal；L85 T4=13 差 47pp、L91 T4=15 差 45pp、L93 T4=17 差 43pp）
  2. **T1/T2 过难**（L51-63 一批 normal 90 目标）：实测只有 37-61（L63 全档 37-42、L61 全档 31-54）
  3. 少数 T3 反而过高（L79/L95 T3=99%、L89 T3=91%）
- **已入库 10 关（L54/57/61/64/72/79/82/83/85/93）bot400 下 0 个全绿**——"入库了"≠"达标了"，bot400 是最终裁判

## 10. 入库记录 vs bot400 全绿复查（78 条：43 绿 / 3 黄 / 32 红）

用户问"查一下我们入库的关卡，跑出来的胜率和关卡数据库的胜率一不一致，是不是真的关卡胜率都是绿色的"：
- 方法：DB 取 `identitySource=='hermes-import'`（85 条）∩ 池子 `source=='bot'` 同四元组匹配 → 78 条
- **只有 43 条真绿（55%），32 条红（41%）**——DB 前端显示绿色 ≠ bot400 真机绿色（summary 数据算的绿是假绿）
- 全绿入库关：**L102/L110/L162/L163**（4 关真全绿）
- 重灾区：L83（T1/T2/T3 红 +19~+34.7）、L61（全档红）、L136（T2/T3/T5 红）、L144（T2/T3 红）、L64/L72（T2/T3 红）、**L174 昨天刚入库就有 3 红**（T2=-45.9/T4=-30.3/T5=-27.6，p0 快验最不可靠）、L120 T5 +44.1、L57 T2 -46.3
- **规律：T5 档普遍红**（93/85/119/120/136/138 都 T5 红）——低档位 summary 最不可靠；p0 快验（174）比 p3 更易翻车

## 11. DB 档位标签语义（L96 案例：为什么一档多条 entry、T3 数据哪来的）

用户问 L96"一个档位为什么有多条 entry"、"T3 呢？"、"显示的 T3 数据是哪来的"——三条 DB 结构事实：

1. **同档位多条 entry 是正常设计，不是错误**：entry 按 `dealFingerprint`（配置指纹）区分，不按档位标签——同档位不同时间导入过**不同配置**，每条配置一个独立 entry。全 DB **173/200 关**存在同档位多条 entry（最多 L100 T5 有 4 条），bootstrap 多次导入+历次探针残留的正常现象。
2. **前端 resolveActiveRun 按 boardFingerprint + dealFingerprint 精确匹配，不看 sourceTierLabels**——多余 entry 不参与匹配，不影响打包（verify_packaging 1000/1000 证明）。
3. **T3 没有标签 entry 但显示有数据 = asset T3 配置匹配到同配置的其他标签 entry**。L96 实证：asset T3/T4 同配置（sd0/10,10,1,1,10/of0.5）→ DB 里该配置 entry 标 T4（wr=40.0%）→ 前端 T3 显示 40.0%。**看某档胜率要按配置（四元组）找，不是按标签找。**

另外：**bootstrap 残留 ≠ 有效入库数据**。L96 的 6 条 entry 全 `bootstrap-current`（无 hermes-import=从未正式入库），DB T2=67.4%（旧牌面）vs bot400 2.5%——牌面已变，bootstrap 旧数据作废，不能当参考。判断"是否入库过"看 `identitySource=='hermes-import'`，不是看有没有 entry。
