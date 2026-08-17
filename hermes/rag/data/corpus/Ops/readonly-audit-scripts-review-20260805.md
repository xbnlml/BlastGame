# 只读审计脚本审查：compare_imported.py / verify_pool_data.py（2026-08-05）

审查对象：`hermes/tools/compare_imported.py`（重选最优档位 vs Excel 入库记录对比）与 `hermes/tools/verify_pool_data.py`（池子数据可靠性核验）。结论：**只读性达标、调用链正确，但 verify_pool_data 有 2 个实质缺陷（of 未归一化=高、来源优先级未建模=中），compare_imported 有 2 个误导性问题（Excel 空记录静默、分类不符坑 117）——修复前输出需人工复核，不能当"应更新"清单直接消费。**

## 一、2026-08-05 实测数据事实（写对比/核验脚本的依据）

- **Excel wr 列（全表）**：715 个数字单元格全为小数（0.753=75.3%）、0 字符串、0 个百分数（>2）、**285 个空单元格**（坑 119 清数据后大量关只剩骨架，Tier2-5 行只有关卡号/难度/档位）。
- **池子 of 字符串写法**：全量 **152 种 distinct repr**；151-200 内 75 种（'0.500'×2014、'0.5'×114、'0'×31、'0.000'×19、'0.7'×12、'0.01'×10…）。→ **任何配置键比较必须用 `pool._config_key`/`_norm_of`（str(float(of))），裸 str(of) 必错（坑 87）**。
- created_at 全为 ISO 字符串含 'T'（'2026-08-03T11:37:35'），字符串比较与 `pool.dedup_records` 一致 ✓。
- ratios 当前无空格（0 例）；`.replace(' ','')` 是防御性的，但 pool._config_key 不归一空格——语义与 pool 不一致（潜伏）。
- board.md：100 行 ✅已入库、难度列小写 normal/hard/superhard、L150 状态为 `—`；正则 `^\|\s*(\d+)\s*\|\s*(\w+)\s*\|\s*(✅已入库)\s*\|` 实测只命中 ✅已入库行（🟡/🔴/—/总结行正确跳过）✓。
- 151-200 池子：1953 个配置组、231 个多记录组、**混合来源组（phase1+verified 同配置）0 例**——B2 缺陷当前不触发，但潜伏。

## 二、verify_pool_data.py 问题（行号按 2026-08-05 版本）

1. **B1【高·坑 87】L79-84：配置键用 `str(r.get('of',''))` 原始字符串**。pool._config_key 归一 of，脚本不归一 → '0.500'/'0.5'/'0' 拆成不同组：① 组内 1 条时漏检 ② 某组 ≥2 条且全组最新记录在另一组（deduped 里）时误报 stale。修：`from tools.data.pool import _config_key` 直接复用（同时消除 ratios 空格语义漂移）。
2. **B2【中】L87-95：stale 判断 `newest = max(grp, key=created_at)` 未建模 `_source_penalty`**。dedup 规则是"同级取新、phase1/2 永不压过 verified"；若组 = phase1（created_at 新）+ bot（旧），dedup 正确保留 bot，脚本却报"未取最新"。修：组内先比 _source_penalty 再比 created_at，或直接断言"deduped 中该 key 的记录 == 按 pool 规则应保留的记录"。
3. **B3【中】不检测 wr=0/games=0 占位垃圾**（能过 filter_verified，见坑）：verified 计数含垃圾、结论"✅ 全部合规"可能掩盖问题。修：`wr<=0` → issues + info 单列 garbage。
4. B4【低】L64 `bad_src` 计算后从未使用（死代码）。

## 三、compare_imported.py 问题

1. **A1【中】L89-90 + L138-141：Excel 无记录/记录不全（len<5）→ old_wrs=None → 静默归入 no_change"无变化"**。全表 285 个空 wr 单元格意味着很多关会显示"无变化"而非"Excel 无记录"，误导核对结论。修：状态分 `excel_missing`/`excel_partial`，像 no_combo 一样单独列出。
2. **A2【中】L138-139：changed 分类只按 `max_diff > threshold(2pp)`**，不符坑 117 定稿（① 同配置新胜率且 >5pp 非波动 ② 重选判定是否优于 Excel——判定不变=不更新）。实测 L153 变化 2.5pp、判定 不合格→不合格 仍被列 changed。verdict_old/verdict_new 已算出（L104-107）却没参与分类。修：判定变化优先（变好且 >2pp → 应更新；判定不变仅 max_diff>5 才提示）。
3. A3【低】L90 裸 `×100` 无类型防御（当前数据全小数安全；历史出过百分数事故坑 107/115，字符串会 TypeError）。修：`float(row[3])` + `abs(v)>2 则 /100`。
4. A4【低】L9 docstring 称 --json"供 reimport_batch 消费"，实际 reimport_batch.py 自己重选（L60-66），不调它；且 JSON 缺 sd/sc/ratios/of 四元组。

## 四、验证正确的部分（✅ 可放心依赖）

- **只读性**：两脚本零写入——openpyxl `read_only=True` 不 save、board/pool 只读、只 import `check_judgment`（纯计算，不碰 _rounds.json，坑 43 合规）、无 git/subprocess 写。冒烟 `--levels 151-156` 无副作用。
- **find_best_monotonic 调用**：`find_best_monotonic(ver, t['tiers'], top_n=1, difficulty=t['diff'])` —— filter_verified 后数据 ✓、difficulty 字符串（坑 44）✓、targets list ✓；返回 `(q, gs, recs5)`（pool.py L322/L358），`res[0][2]`=recs5 ✓；`_bucket` 已含 wr>=5 硬过滤 ✓。
- **check_judgment 调用**：combo `{T1..T5: 百分数}`、diff 字符串、targets list，取 `[0]`=result ✓；判定用未取整精确值（坑 31b）✓；`totalGames` 字段名与 pool 一致 ✓。
- **board 正则**：只匹配行首 `| 关卡 | 难度 | ✅已入库 |`（坑 99/118 格式）✓。
- Excel 多组记录：read_excel 按行覆盖，最后一块（最新组）胜出，与"备注非空=最新组"规则一致 ✓。

## 五、审查方法（可复用）

1. **对照真源逐行核对**：脚本逻辑 vs pool.py 的 `_config_key`/`_source_penalty`/`dedup_records` 语义（去重键、来源罚、created_at 比较方式）。
2. **量化验证**：用 python 复刻脚本的 stale 检查跑 151-200 全量，统计误报/漏报（本次：raw-of 0 触发但 75 种 of 写法证明风险真实；混合来源组 0 例证明 B2 潜伏——"当前不触发"≠"逻辑正确"）。
3. **数据画像**：Excel 全表类型扫描（字符串/百分数/空值计数）+ 池子 of/ratios/created_at 类型分布——写死假设前先验证数据形态。
4. **冒烟**：小范围（151-156）实跑确认无副作用、输出格式符合预期。
