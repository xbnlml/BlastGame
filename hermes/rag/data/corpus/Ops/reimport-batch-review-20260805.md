# reimport_batch.py 审查记录（2026-08-05）

编排层脚本 `hermes/tools/reimport_batch.py`（重选 → reimport JSON → reimport.py 落盘 → gen_payload → node write_level_db*.mjs 一条龙）的完整审查。方法：对照 reimport.py / gen_payload.py / pool.py / asset_patcher.py / write_excel.py / leveldb_sync 两个 mjs 逐一核对契约 + 实测 dry-run（L158 normal + L174 hard）、L999 无目标跳过、tmp 残留行为。

## 验证通过的契约（可放心依赖）

- **idx 展开正确**：`find_best_monotonic`（pool.py L329）返回 `[(q, gs, recs5)]`，recs5 **恒为 5 档**——Normal 3-tier 分支返回 `[r1,r1,r3,r5,r5]`（L351），所以 `idx=[0,2,4]` 取 T1/T3/T5 正确；reimport.py `_normal_expand_tiers`（L61-62）展开 `[t1,dict(t1),t3,t5,dict(t5)]` 一致。write_tiers 内部对 normal 的二次展开结果等价（T2/T5 备注清空）。实测 L158：JSON 3 套 → 预览 5 档 76.2/76.2/60.3/42.8/42.8。
- **wr 单位链无冲突**：池子 wr 百分数 → reimport JSON 'wr' 百分数 → reimport.py `wr/100` 转小数写 Excel（坑 115）；gen_payload **读 asset 不读 JSON**（read_ddc + 池子同配置 `match['wr']/100`）→ payload 小数；board 显示百分数。三条链独立且单位各自正确。
- **JSON 字段契约**：`{lv: {diff, targets, date, note, tiers: [{wr,sd,sc,ratios,of,note}]}}` 与 reimport.py 消费字段逐一匹配（status 可选，默认 '✅已入库'）。
- **gen_payload 输出默认 `_write_payload.json`** = dryrun/write mjs 硬编码读取路径（坑 96 要求满足，write_level_db_dryrun.mjs L15）。
- **跳过不中断**：无目标关 → print 跳过 → cfg 空 → exit 1，且空 cfg 时**不写** tmp JSON（L122 exit 在 L126 json.dump 之前）✓。
- get_target 返回 `{'diff': str, 'tiers': [float×100]}`；Excel 浮点误差如 55.00000000000001 被 `int()` 截断正确。
- board 更新/Excel 备份/重跑幂等（write_ddc/write_tiers/board 均就地更新）✓。

## P1 缺陷（修复前 --apply 不宜当一键工具）

1. **部分关 FAIL 仍写 DB**：reimport.py 各动作失败只记 results（L149-157）不 exit 非 0 → reimport_batch 的 run()（L97-105）只看 returncode 放行 → gen_payload 读**旧 asset** 生成 payload 写 DB。FAIL 关旧配置静默入库，asset/Excel/DB 三方不一致且无人察觉。修复：reimport.py FAIL>0 时 exit 1，或 reimport_batch 解析输出含 '❌'/'FAIL' 即中止。
2. **被跳过关仍进 payload**：reimport_batch L149 `lvs_str` 用**原始请求 lvs** 而非 cfg 成功关——build_config 跳过（池子无组合）的关若 asset 能匹配池子同配置记录，仍会生成 payload 写 DB（该关根本没落盘）。修复：用 `sorted(cfg.keys())` 生成 lvs_str。
3. **dryrun FAIL 不阻断 write**：write_level_db_dryrun.mjs 有 FAIL 也 exit 0（只打印，L49-55），步骤 4/5 之间无闸门——"每步验证"形同虚设。修复：解析 dryrun stdout（'失败 N' >0 中止）。

## P2 缺陷

- **tmp JSON**：`project-state/reimport_batch_tmp.json` 固定名 + 永不清理（实测残留）；误用风险：手动 `reimport.py --config reimport_batch_tmp.json`（不带 --dry-run）会把上次 dry-run 的**旧快照**真实落盘，文件无时间戳/批次标识无法分辨新旧。docstring（L12）声称 dry-run"不写任何文件"与实际不符——步骤 1 无条件 json.dump。修复：文件名带时间戳 / 退出时删除 / 写前存在则警告。
- 单关无 try/except：find_best_monotonic 抛异常中断整批（违反"某关失败跳过不中断"容错铁则）。
- run() 无 timeout（坑 112 教训：subprocess timeout 必须 > 实测最慢路径，否则挂起永久阻塞）。
- 硬编码 'python' 而非 sys.executable（实测解析到 hermes venv 3.11.15；用户用 python3 3.13.2 启动时子进程换解释器，依赖混装有风险）。
- gen_payload `imported_at` 硬编码 '2026-08-05T16:00:00.000Z'、`--source` 默认同名 'hermes-import-20260805.csv'——每批同标识，DB 批次难区分（坑 93 的 sourceFileName 匹配验证会混淆）。
- parse_levels 遇 '158-'（缺右端）/ 'a-b' 抛裸 ValueError；r 缺 'totalGames' 键时备注变 'None局'。
- 两个 mjs 内 REPO 硬编码 `C:/Users/Administrator/Documents/BlastGame`（项目现状，非本脚本引入，REPO 移动即断）。

## 实测命令（可复现）

```bash
python tools/reimport_batch.py --levels 158,174 --dry-run   # normal+hard 各一关：验证 3套→5档展开与预览
python tools/reimport_batch.py --levels 999 --dry-run       # 无目标跳过 + 空 cfg exit 1（不写 tmp）
```
注意：dry-run 会**覆盖** tmp JSON——测试前先备份 `project-state/reimport_batch_tmp.json`，测完恢复。
