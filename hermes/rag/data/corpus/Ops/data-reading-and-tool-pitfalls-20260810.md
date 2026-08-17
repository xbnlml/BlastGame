# 2026-08-10 数据读取与工具坑（L57 持续调优会话）

## 1. campaign-summary CSV 列名（bot 批跑原始数据）

`telemetry/bot/<lv>-<lv>-<ts>/L<lv>-<lv>-T<n>-<ts>-batch-range/campaign-summary-L<lv>-<lv>-T<n>.csv`

- 列名是**小写**：`startDifficulty / shuffleSplitCount / shuffleSplitRatios / shuffleOverflowFactor / winCount / failCount / DifficultyLevel`
- **没有 WinRate / totalGames 列**——胜率 = `winCount / (winCount + failCount) * 100`（读 `WinRate` 或 `TotalGames` 会拿到 0/None 误判 0%）
- 表头带 BOM（`\ufeffLevelGroup`）→ 用 `encoding='utf-8-sig'`
- ratios 带引号（`"10,10,0,10,0"`）→ csv 读取正常，无需特殊处理

## 2. phase1/phase2 高胜率是噪声，验证必须 200 局重跑

**L57 完整证据链**（同配置/同方向跨局数）：

| 局数 | 结果 |
|---|---|
| phase1 40-60 局 | 98-100%（极重噪声） |
| phase2 200 局 | 71.5-75.5%（仍偏高） |
| 200 局重跑 / phase3 370 局 | 45.5-64%（真值） |

- phase1 的 98-100% 配置 200 局重跑后全部跌到 45.5-52%（-48~-52pp）
- phase2 的 71.5%（0,0,0,10,10）200 局重跑后 53.5%（-18pp）
- **教训**：用户说"试 phase2 90+/更高胜率的"时，正确做法 = 把这些配置 **200 局重跑验证真实值**（不是采信 phase1/2 的数值），用 campaign-summary 的 winCount/failCount 算
- phase1 高值配置的"变体"（换 ratios 位置/微调 of）也要 200 局验证——变体不等于原配置

## 3. reimport.py 自动 DB 同步失效（2026-08-10 L163 案例）

- reimport.py 输出 "✅ LevelDatabase 同步完成" 但 **test.json 实际没写入新 entry**（L163 入库后 DB 还是旧 4 条）
- **验证**：reimport 完成后必须查 DB（`db['levels'][lv]['entries']` 里有无 `reimport-YYYYMMDD-<lv>` sourceFileName 的 entry）；没有 → 手动 `write_level_db.mjs` 补写（构造 `_write_payload.json`，见 6cc）
- 补写后 "3/5 档" 是 normal dedup 正常现象（T1=T2/T4=T5 同配置合并），不是失败

## 4. 池子 wr 单位：百分数（不是小数）

- stage-data JSON 里 wr 存**百分数**（72.5 表示 72.5%），不是 0.725
- 读池子记录时**不要 ×100**（会得 7250 误判"数据放大"）；直接 `r['wr']` 当百分数用
- 入库/Excel 用小数（0.725），池子/DB 用百分数（72.5）——转换只在边界做一次

## 5. 其他工具修复（本次会话，已落地）

- **judge_level.py 改关卡分支**：`rnd = inc_round(lv)`（原 `inc_round(lv)` 不赋值 → 返回旧轮数 → auto_loop 的 `round >= MAX_ROUNDS` 检查失效，L85 满 6 轮仍留 pending 显示 r5/6）
- **auto_loop extract_json**：planner 输出多行 JSON + debug 文本混合，原只支持单行 → 加 brace-span 提取（first `{` .. last `}` 再 json.loads），支持多行 JSON
- **write_level_db.mjs / compare_level_db.py find_asset_path 分段**：真实分段是 `1_20/21_40/41_60/.../181_200`（不是 `1_60`）；分段错 → 找不到 asset → boardFingerprint 算错 → DB entry 用错误 fingerprint
- **compare_level_db.py of 比较**：DB 存 `'0.500'`、asset 存 `0.5` → 字符串比较全失败（曾误报 93 关全白）→ of 转 float 容差比较
- **DB 同配置新旧 entry**：asset 配置匹配 entry 时可能命中旧 campaign entry（如 L54 T3 35.9% vs 新 51.2%）→ 按 boardFingerprint 过滤 + 取最新 importedAt
