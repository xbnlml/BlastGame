# 打包前一致性验证 + 调优期 DB 白机制（2026-08-10）

## 打包前必跑（用户：打包用当前 asset，必须和关卡数据库胜率对应，功亏一篑级别）

```bash
python tools/verify_asset_db_match.py          # 全扫 1-200
node tools/leveldb_sync/verify_packaging.mjs    # 官方 resolveActiveRun 路径终极验证
```

- `verify_asset_db_match.py`：直接比参数——asset 每档 (sd/sc/ratios/of) 四元组 → DB 找同参数 entry（同 boardFingerprint）→ winRate。`--levels` 指定、`--show` 摘要；不一致退出码 1。
- `verify_packaging.mjs`：模拟打包/前端查询——asset 配置 → dealFingerprint → `resolveActiveRun`（boardFingerprint+dealFingerprint 精确匹配）→ entry winRate。匹配到的 winRate 就是前端显示的胜率。
- **reimport.py 入库后已自动调用 verify_asset_db_match**（无需手动）。
- 用户偏好：**验证要直接比配置参数（sd/sc/ratios/of），不要绕 fingerprint**（"你不能直接比配置？也就是难度参数"）。

## 调优期 DB 变白是机制必然（2026-08-10 用户问"不能在不变白的情况下调优吗"）

- **原因**：auto_loop Phase2 `apply_probes` 把探针配置写入 asset → asset 配置变 → dealFingerprint 变 → DB 前端按 asset 配置匹配 entry → 匹配不上 → 显示白。Unity 批跑只读 asset，无法外部传配置 → **机制无法避免**。
- **数据不会丢**（用户真实担忧是"找不回当时数据"）：
  1. `assets_backup/{lv}.asset.bak`（write_ddc 写前自动备份）
  2. `project-state/pre_tune_backup_<date>/`（auto_loop round1 自动备份，2026-08-10 起）
  3. DB entry 原样保留（test.json 里 reimport entry 未删，只是 asset 临时匹配不上）
  4. Excel 入库记录（手动挑配置记录.xlsx）
- **调优完处理**：合格 → reimport 新配置（恢复绿）；不合适 → 用 .bak 恢复原 asset（DB 立即恢复匹配）。

## 工具 bug 修复链（2026-08-08/10，同坑别重踩）

1. **asset 分段规则**：`test/` 下真实分段是 `1_20/21_40/41_60/61_80/81_100/101_120/121_140/141_160/161_180/181_200`（**不是 1_60**）。compare_level_db.py 和 write_level_db.mjs 都犯过 `n<=60 → '1_60'` 的错 → 找不到 asset → os.walk 兜底找到 funnel_b 或其他 → boardFingerprint 算错。分段函数必须精确。
2. **of 匹配必须 float 容差**：DB 存 `'0.500'`（字符串）、asset 存 `0.5`——`str()` 直接比永远不匹配（曾误判 93 关全白）。`config_key`/`deal_key` 里 of 统一 `float(of or 0)`。
3. **judge_level.py 轮数 bug**：改关卡分支 `inc_round(lv)` 返回值必须赋给 `rnd`（`rnd = inc_round(lv)`），否则返回旧轮数 → auto_loop 的 MAX ROUNDS 检查失效 → 跑满 6 轮仍留 pending。
4. **auto_loop extract_json**：planner 输出多行 JSON + debug 噪声 → extract_json 需 brace-span 提取（first `{` .. last `}`），支持多行。
5. **probe_configs.json 禁止 write_file 整体覆盖**（2026-08-10 L57 实战）：它是共享配置（可含多关探针），`write_file` 整体替换会丢掉其他关的探针配置。修改必须走 `apply_probes.py` / `design_probes.py --write`（或先读后合并再写）。手动设计探针（如 L57 打 75 段）时：先读现有文件 → 只更新目标关 → 写回，且写前用池子 dedup 检查 5 槽是否"未验证过的新变体"（不重跑旧配置）。

## 一致性检查陷阱（2026-08-10 用户纠正"哪有极低的winrate"）

- **绝不要遍历 DB 全部 entry 报"asset 不一致"**——DB 有大量历史残留 entry（campaign-summary/summary csv 旧数据，winRate 可低至 0.01-0.05，dealFingerprint 与当前 asset 不同）。前端/打包按 fingerprint 精确匹配**只显示 asset 配置对应的 entry**，残留 entry 永远不会被显示。曾误报"287 条不一致"惹怒用户。
- **正确检查 = 只走 asset→resolveActiveRun 路径**（`verify_packaging.mjs`）：asset 每档配置 → dealFingerprint → entry winRate>0。残留 entry 不删也不影响打包。
- **wr 单位对照（误报源头）**：池子 stage-data JSON = **百分数**（44.75）；DB test.json winRate = **小数**（0.4475）；summary CSV VerifiedWinRate = 小数（0.4475）。分析脚本展示时按各自单位取值，**禁止对池子 wr 再 ×100**（曾把 72.5 显示成 7250 误判"数据污染"）。

## 讨论关卡前先查 board 当前状态（2026-08-10）

- 用户问"57 为什么 75% 不可行要改关卡"——实际 L57 **已入库**（93.3/93.3/64.0/49.0/49.0），从未被标改关卡。教训：讨论"为什么改关卡/为什么不可行"前，先 `grep board.md` 确认该关当前状态（已入库/待调优/待改关卡）和入库记录，不要凭旧判定或 auto_loop 日志下结论。
- 黄关（如 L163 T4/T5=39 差 50 目标 11pp）由 auto_loop 探针自动解决（探针探 40-50 段），**不要主动提议用池子某配置替换**——探针流程会自己找。


- **sd=0 不洗牌只对 normal**（difficultyLevel=0）：`index = max(0,difficultyLevel)×factor + sd`，`numToShuffle = ceil(index/100×size)`。normal 关 difficultyLevel=0 → index=0 → 零洗牌 → ratios 无区分度。
- **hard/superhard 关 difficultyLevel>0 → sd=0 也洗牌** → ratios 有区分度。
- 教训：**别拿单关（normal）数据推广到所有难度**。探针裁剪（如"sd=0 只跑 1 个"）必须按难度区分或数据驱动（段覆盖判断），不能一刀切。
