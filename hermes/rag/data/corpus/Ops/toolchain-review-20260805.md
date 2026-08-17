# 2026-08-05 gen_payload.py / clear_excel_data.py 逐行审查（坑 123/124/125）

审查对象：`hermes/tools/gen_payload.py`（通用 payload 生成，替代 gen_payload_* 变体）+ `hermes/tools/clear_excel_data.py`（清 Excel 数据列保留骨架）。
全部发现均经实测验证（dry-run 实跑、gen_payload 端到端、池子 7224 条扫描、官方 Run/test.json 抽查、Excel 200 关全表扫描）。

## gen_payload.py

| 行号 | 问题 | 严重度 | 修复 |
|------|------|--------|------|
| L51+L62 | **真实崩溃 bug**：`read_ddc` 失败返回错误字符串（`'missing C:\...'` / `'找不到 DynamicDifficultyConfigs'` / `'找不到结束标记'`），`if not asset:` 拦不住（字符串 truthy）→ `enumerate(asset)` 逐字符迭代 → `cfg['sd']` 抛 `TypeError: string indices must be integers`。实测 `--levels 999` 复现 | **高** | `if not isinstance(asset, list) or not asset:` |
| L69-72 | OVERRIDE 值无范围校验：误传百分数 83.3（应为 0.833）会写 8330% 进 DB，dryrun 只验 upsert 不拦 | 中 | `if not (0 < wr <= 1): 报错退出` |
| L69 | OVERRIDE 优先级在池子匹配之前且无覆盖警告——override 键写错档位时静默替换好数据 | 低 | 先算 match，命中时打印 `(OVERRIDE 覆盖: 池子原为 X%)` |
| L69 | override 值非 dict（如 `{"155": 0.833}`）→ `str(i) in 0.833` 抛 TypeError | 低 | `isinstance(override[str(lv)], dict)` 校验 |
| L114 | `--imported-at` 默认硬编码 `'2026-08-05T16:00:00.000Z'`——日期过期（同日 6lv 脚本已从 10:00 漂到 16:00），日后跑写错时间戳（DB 按 importedAt 排序/剪枝） | 中 | 默认 `datetime.now(timezone.utc)` |
| L88-90 | 单档无匹配整关跳过但 exit 0，调用方易漏看 | 低 | skipped>0 时 exit 1 或显著汇总 |
| L76-80 | ✅ of 比较已 float 归一化（坑 87）：`abs(float(r.get('of',0) or 0) - float(cfg['of'] or 0)) < 1e-6` 双侧 float+ε；sd/sc/ratios 双侧 `str().strip()`。实测 L155 T3 池子 of='0'（字符串）vs asset 0.0 匹配成功；L158 of='0.500' vs 0.5 成功 | — | 无需改 |
| L42-43 | `norm_ratios` 只整体 strip 不逐段 strip（`'1, 0, 1'` 失配）——扫描 7224 条池子记录 0 条含空格/全角逗号，休眠风险 | 低 | 逐段 strip 防御 |
| L54 | dedup 的 key 用原始 ratios 字符串（不含全角归一化），全角变体可绕过 dedup 同配置两条并存、首条胜出不定 | 低 | 同上，或 dedup key 也归一化 |
| L84 | `match['wr']/100`——wr 是浮点 ✓；若未来适配器产出字符串 wr 会 TypeError | 低 | `float()` 防御 |
| L97-103 | ✅ payload 5 字段与 write_level_db.mjs L30-43 读取键名逐一吻合；mjs 补 fingerprint（同一对象上计算，无坑 93 自复现偏差）+sourceFormat:'B'+perTierMeta+lastResolvedAt 构成 9 字段 entry；dryrun L61 的 9 字段校验集（fingerprint/tierConfigs/tierWinRates/tierFailDistribution/importedAt/sourceFileName/sourceFormat/perTierMeta/lastResolvedAt）与 mjs 构造一致；tierFailDistribution 5 元素/每档 10 段串与官方 Run/test.json 现有 entry（抽查 L1）格式一致 | — | 无需改 |
| L91-92 | FBD 语义近似（非 bug，项目已接受）：匹配记录的 failBucketDistribution 来自 dedup 胜出记录的批次/档位（dedup key 无 tier），Normal 关 T1=T2 同配置写同一条 FBD 到两档（当前 L158 payload 即如此） | 提示 | 文档注明即可 |
| L128-129 | `open()` 无 with、非原子写，异常留半截文件 | 低 | `with` + tmp+rename |

## clear_excel_data.py

| 行号 | 问题 | 严重度 | 修复 |
|------|------|--------|------|
| L49-68 | **"先写后验"**：L66 `wb.save()` 在 L71+ 验证之前——验证失败（行数≠5/档位列错/首行缺失）时文件已被清空保存、无回滚，输出 ❌ 但为时已晚 | **高** | 结构验证提前到 save 之前（内存 workbook 上跑 dry 验证），失败 abort；或失败时从备份恢复 |
| L44-45 | 备份名仅秒级时间戳 `_before_clear_HHMMSS.bak`：跨天同秒必覆盖旧备份（8-04 15:30:22 与 8-05 15:30:22 同名）；与项目约定不符（历史 13 个备份全部带语义标签，如 `_before_clear16_150302.bak`） | 中 | `_before_clear_%Y%m%d_%H%M%S.bak` + 存在则追加序号 |
| L45 | `.bak` 后缀 openpyxl 无法直接读回（坑 107），回滚需先改名 .xlsx | 低 | 备份名用 `.xlsx` 后缀或文档注明 |
| L71-77 | 验证循环 `cur2 = int(row[0])` 无 isinstance 守卫（L56 清空循环有、验证循环没有，不对称）——列 A 出现任何非数字文本 → ValueError 崩溃 | 中 | 与 L56 相同守卫 |
| L85 | 严格 `len(rows) != 5`：当前 200 关全单组 5 行 ✓（全表实测）；若某关历史有两组记录（坑 107 分组规则）会清两组后验证失败 | 低 | `len(rows) % 5 == 0`（或由前置验证兜底） |
| L58/L78 | `startswith('Tier')` 判断：档位为数字 1-5 的旧数据行（坑 107 追加模式产物）被静默跳过，真实模式保存后才报"0 行" | 低 | 接受 1-5 数字或报错 |
| L97 | `r[3:]` 覆盖第 10 列以后，未来加列误报"数据列未清空"；当前 max_col=9 对齐 ✓ | 低 | `r[3:9]` 限定 |
| L63 | dry-run 下打印"找到并清空 N 行"措辞误导（实际未清） | 低 | 改"将清空 N 行" |
| L41-68 | ✅ dry-run 确实零写入（实测）：跳过备份、跳过清单元格、跳过 save，仅 load+close，无 .bak 产生、xlsx mtime 不变；验证在 dry-run 下只查结构不查数据列 ✓ 合理；首行关卡号+难度、5 行、Tier1-5 档位列三项验证正确实现（只查 Tier1 行难度非空，符合坑 119） | — | 无需改 |
| L49 | `load_workbook` 无文件存在检查 → FileNotFoundError traceback | 低 | `os.path.exists` + 友好报错 |
| L66 | `wb.save` 非原子写（直接写原文件），中断可能损坏 Excel | 低 | tmp+rename（备份已存在可恢复） |

## 实测复现命令（供验证修复）

```bash
# gen_payload asset 缺失崩溃（修复前）
python tools/gen_payload.py --levels 999 --source t.csv --out /tmp/x.json
# → TypeError: string indices must be integers（L62）

# OVERRIDE 正常路径（L155 实测：T1/T2=83.30% OVERRIDE，T3-T5 池子匹配）
python tools/gen_payload.py --levels 155 --source t.csv --override '{"155": {"0": 0.833, "1": 0.833}}' --out /tmp/x.json

# clear_excel_data dry-run（零写入，102/110 各 5 行结构验证通过）
python tools/clear_excel_data.py --levels 102,110 --dry-run
```

## 结论状态（2026-08-05）

P0/高：gen_payload L51 isinstance 判断、clear_excel_data 前置验证。P1/中：OVERRIDE 范围校验、imported-at 默认 now、备份命名加日期、验证循环 isinstance 守卫。其余低优先。修复前两脚本核心路径可用（gen_payload 正常关可用、clear dry-run 可用），修复后可交付。
