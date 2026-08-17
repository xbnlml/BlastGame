# 工具链全面审计（2026-08-07）

对 design_probes / judge_level / apply_probes / reimport / auto_loop / asset_patcher / pool / compare_level_db / warden 的全面审计结论。行号以审计当日磁盘版本为准，之后可能漂移——按「问题类型」而非行号复用。

## 当前最值得警惕的「防线失效」类隐患（历史 bug 的最后兜底）

这些是 L130/132/133/153/154 那类探针 bug 的最终防线，均未补齐，优先级最高：

1. **Warden W02 只查 `len(tiers)==5`，不查 ratios 质量**（重复/空/目标不匹配）。
   - warden.py `check_5_slots` 仅数量；apply_probes.py `warden_check` 也只调 `check_5_slots`。
   - 脏 ratios 会直达 Unity，被 Unity dedup 吃槽（历史多起事故根因）。
2. **Wardn W06 `check_asset_hash` 空转**：只 `level_sig()` 并检查非 None，从不与历史快照比对，名为"快照一致"实则不校验。
3. **Warden W07/W08 正则永不匹配 board 格式，静默失效**：`re.search(r'## 🟢 已入库...')` 匹配的是分区块格式，但当前 board.md 是「状态列表格」（`✅已入库` 在状态列，无区块头）。→ board 冲突/探针-已入库混用检查永远通过。
4. **auto_loop 调 warden 不带 `--probe-file`** → `tiers_map` 空 → W02 循环零次，5 槽完整性在 auto_loop 路径从不校验。
5. **pool.dedup_records 键类型不归一化**：pool.py:149 用原始 sd/sc 类型作键；`_config_key`（pool.py:18）已统一 str()。read_ddc(int) 与池子(str) 混合时同配置不合并 → 重复配置多填槽位。

## 其它值得留意的点

- **auto_loop `traceback` 未 import**：run_cmd 异常分支调 `traceback.print_exc()`，缺 import → 意外异常路径 NameError 崩溃整批。
- **auto_loop 双轨轮次管理**：主循环 range(1,7) 与 `_rounds.json` 双轨，启动不 reset `_rounds.json`，中断重跑会残留旧轮次直接触发"改关卡/合格"。
- **judge_level `near_tolerance_pp` 逻辑冗余**：L142-151 的 `gap < near_lo - near_tolerance_pp: fail` 分支实际被后面的 `elif gap < ok_lo` 全部接管，near_tolerance 只在极端区间重叠时有意义。L152 案例实际是 `tolerance_pp=2`（elif 内）救回。
- **reimport 三库落盘非原子**：write_ddc→write_tiers→board 顺序执行，中途失败不回滚已写 asset；board.md 无 .bak（asset/Excel 有）。
- **design_probes 大片死代码**：`_design_gap_focused`/`_design_from_knowledge`/`_design_probe`/`_design_placeholder`/`_make_config` 在主 `design()` 流程完全不被调用，可清理。
- **compare_level_db 难度列恒空**：`asset[0].get("_diff","")` 无此字段，纯显示问题。

## 已确认正确的关键点（别再改回去）

- design_probes：目标胜率从 Excel `et.get_target` 读（superhard 不再硬编码）；段内(±5)无候选→交给 fill_remaining，**绝不做段外 ±15 硬凑**；ratios strip+去重+空值兜底。
- judge_level：targets 从 Excel 读真实值；find_best_combo 已过滤 <10 局 test 残留。
- reimport：Excel 胜率正确转小数（`round(t['wr']/100,4)`，0.8=80%）；board 整行 7 列替换匹配当前格式；自动备份 Excel。
- asset_patcher：write_ddc 恢复 mtime（`os.utime`，时间防线依赖）；validate_tiers 覆盖 5 槽/sd/sc/of；写后三重校验+回滚。
- pool：filter_verified 只按来源过滤（不卡局数，局数过滤由调用方加）；`_source_penalty` 同级来源罚分全 0、去重时新数据优先。
- compare_level_db：norm_ratios 正确处理 DB 数组 vs asset 字符串（统一转 int 列表）。
- auto_loop：入库不自动执行（只打标+记最优组合日志，等用户确认走 reimport）；`best_tiers` 局部变量不污染全局 tiers。

## board.md 当前格式备忘

- 表头：`| 关 | 难度 | 状态 | 入库日期 | 目标 | 最优档位 WR% | 备注 |`，7 列整行。
- 状态用状态列（`✅已入库`/`🟡待调优`/`🔴需改关卡`），不是分区块头。W07/W08 若要修，应解析状态列而非匹配 `## 🟢 已入库`。