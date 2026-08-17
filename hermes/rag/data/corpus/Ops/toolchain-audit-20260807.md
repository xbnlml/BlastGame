# 工具链全面审计（2026-08-07）

> 触发：全自动调优暴露多 bug 后，系统性排查 tools/ 与 scripts/。结论：**未发现 P0 bug**（必然导致数据污染/批跑失败），但有多处"防线失效"类 P1。

## 已修复（P1）

### 1. apply_probes 探针质量防线缺失（最严重）
- **问题**：`warden_check` 只查 `check_5_slots`（5 槽完整），不查 ratios 质量。坏探针（ratios 全 `10,1,1,1,1` / 空 ratios / 四元组重复）溜过 → Unity dedup 按 ratios 吃槽 → 实际只跑 1 档。
- **修复**：新增 `warden.check_probe_quality`（W09），apply_probes 挂上。检查：
  1. 5 槽 ratios 非空
  2. 5 槽 ratios 不全相同（`len(set) < 2` 拦）
  3. 四元组 config_key 不重复（完全相同的配置会被 Unity dedup 吃）
- 已 5/5 ad-hoc 验证。

### 2. warden.py W07/W08 正则与 board 格式不匹配（静默失效）
- **问题**：`check_board_conflict`/`check_probe_vs_verify` 用 `## 🟢 已入库` 区块正则，但 board 已改**表格格式**（每行 `| 51 | normal | ✅已入库 |`），无区块头 → 正则永远匹配不到 → 返回空 imported 集合 → **W07/W08 永远通过（静默失效）**。
- **修复**：新增 `_imported_levels()` 从表格行解析 `✅已入库` 关卡号，W07/W08 共用。

### 3. warden.py W06 check_asset_hash 被误删 → NameError
- **问题**：函数被删但 rules.json 仍配 W06、run_warden 仍调用 → 每次 W06 抛 `name 'check_asset_hash' is not defined`（被 except 吞成"检查异常"）。
- **修复**：恢复函数（校验 asset 可读 + level_sig 牌面签名）。

### 4. stage_status.py 依赖废弃 progress.json
- **问题**：progress.json 已废弃（board.md 是状态真源），但代码仍读它 → progress={} → 所有关进 no_data → 只打印标题无内容。
- **修复**：改为从 board.md 表格行解析状态（✅=done / 🟡🔴=need_tuning / 其他=no_data）。修复后正常输出 `Done=102 Tuning=11 NoData=37`。

## 审计确认正确（无需改）

- **judge_level**：targets 从 Excel 读（superhard 不再硬编码 70/55/40/30/20）；`_load_rules()` 返回 `judge_rules` 下层（最后 `.get('judge_rules',{})`），所以 `_load_rules().get('target_deviation')` 读的是 judge_rules.target_deviation（正确）；容差配置 tolerance_pp=2 / near_tolerance_pp=1 / target_deviation.max=15 都在 judge_rules 下。
- **reimport**：Excel 胜率正确转小数（wr/100，坑 115）；board 固定 7 列整行替换；write_ddc + verify_asset；自动备份。
- **asset_patcher.write_ddc**：写后 os.utime 恢复 mtime（时间防线）；validate_tiers 校验空 ratios（validate_tier 有 `if not ratios: errors.append('ratios 缺失')`）。
- **auto_loop**：铁则正确（全自动不自动入库/改关卡，只标记待确认；tiers 局部变量修复）。
- **pool.filter_verified**：只按来源过滤（bot/summary/phase0），不卡局数；局数过滤由调用方各加 ≥10（design_probes/judge_level 已加）。

## P1/P2 已处理（第二轮，2026-08-07 主 agent 自查）

- **P1 `pool.dedup_records` 键类型不统一**：改用 `_config_key`（sd/sc 统一 str）——read_ddc 返回 int(sd=20) vs 池子 str('20') 之前判为两条，导致重复配置。这是 `_config_key` 修复（2026-08-06）的同类问题漏网在 dedup 上。
- **P1 `auto_loop` 缺 `import traceback`**（第191行用却未 import）→ 异常路径崩溃。已补。
- **P1 `auto_loop` 调 Warden 不传 `--probe-file`** → tiers_map 空 → W02/W09 空转。已传 probe_configs.json。
- **P2 `reimport` board 无自动备份**：`_update_board` 写前 `shutil.copy2` 备份（Excel 已有备份，board 补上）。
- **P2 `compare_level_db` 难度列恒空**（`asset[0].get("_diff")` 无此字段）：改从 `excel_target.get_target()` 读 diff。
- **P2 `warden W05` 全行扫描误伤**：注释/docstring 里的 'git reset' 被当危险命令 → 批跑被错误 BLOCK。改 AST 只检查 `subprocess/os.system/os.popen` 调用实参里的 git。
- **P2 `stage_status` progress.json**：见上（已修）。

## 有意不改（避免引入新风险）

- **judge_level `near_tolerance_pp`**（审计 B3 说冗余）：实际影响判定边界（L153 gap=12.9 判接近依赖它），改会改变判定结果，不动。
- **design_probes 死代码**（`_design_gap_focused`/`_design_from_knowledge` 等互引不用）：agent_analyze 依赖 `_design_probes`，怕误删破坏，暂缓。

## 核心教训

1. **防线必须查"质量"不查"数量"**——只查 5 槽完整拦不住坏探针。Warden 要查 ratios 去重/非空/四元组不重复。
2. **工具与数据格式同源维护**——board 从区块改表格后，所有用正则解析 board 的工具（warden/stage_status）都要同步改，否则静默失效（不报错但永远通过/无内容）。
3. **删函数要删干净**——rules.json 还配 W06 但函数被删 → NameError 被吞成假"检查异常"，掩盖真实问题。
4. **审计方法**：大数据量工具链审计，派子 agent 并行深查 + 主 agent 自查高频工具（judge/apply_probes/reimport/warden），交叉验证。子 agent 报告存 UTF-16 文件读取需正确解码（乱码时从 live transcript 的 final summary 提取）。