# 打包前 asset↔关卡数据库一致性验证（2026-08-10 落地）

## 用户要求（原话）
"我们马上要用关卡数据库里的配置打包，你一定要确保当前的asset和关卡数据库上的胜率是对应的"、
"我不管数据源，只要保证当前asset里的参数都是关卡数据库里看到的这些胜率对应的参数就行了"。
打包 = 用当前 asset 打包，DB 显示的胜率必须就是 asset 这套参数的胜率。

## 两个验证工具（打包前必跑，别再手写脚本）

1. **`tools/verify_asset_db_match.py`** — 直接比参数
   - asset 每档 (sd, sc, ratios, of) 四元组 → DB 找**参数完全一致**的 entry（同 boardFingerprint）→ 输出 winRate
   - `--levels 54,61` 指定关 / `--show` 输出胜率摘要 / 默认全扫 1-200
   - 不一致退出码 1（asset 参数无同参数 entry / winRate 无效）
   - 已集成进 `reimport.py`：入库完成后自动调用（不用再手写验证脚本）

2. **`tools/leveldb_sync/verify_packaging.mjs`** — 官方路径终极验证
   - asset 每档配置 → dealFingerprint → `resolveActiveRun`（boardFingerprint+dealFingerprint 精确匹配，前端/打包实际路径）→ entry winRate
   - `node tools/leveldb_sync/verify_packaging.mjs --levels=54,61`
   - 匹配到的 winRate 就是打包/前端显示的胜率

打包前跑这两条，任何 asset↔DB 不一致都会被抓住。

## DB 匹配三大坑（2026-08-08/10 修复，全踩过）

1. **asset 分段规则**：`test/` 下是 `1_20/21_40/41_60/61_80/81_100/101_120/121_140/141_160/161_180/181_200`。
   `n<=60 → '1_60'` 是错的（不存在），必须 `n<=20→1_20 / n<=40→21_40 / n<=60→41_60`。
   compare_level_db.py 和 write_level_db.mjs 都犯过此 bug → 找不到 asset → boardFingerprint 算错（L54 写入错误 bf 案例）。

2. **of 字符串比较**：DB dealConfig 的 shuffleOverflowFactor 存 `'0.500'`，asset 存 `0.5`——`str()` 直接比永远不等（曾导致 93 关误判全白）。
   必须转 float 容差比较（`abs(float(a)-float(b)) < 1e-6`）。

3. **同配置新旧 entry**：同一 dealConfig 可能有多条 entry（旧 campaign-summary + 新 reimport）。
   匹配必须取**最新 importedAt**（或按 sourceFileName 过滤 reimport），否则取到旧值（L54 T3=35.9 旧 vs 51.2 新）。
   前端 resolveActiveRun 按 fingerprint 精确匹配天然取到正确的；手写脚本要自己排序。

## 调优期 DB 白（机制必然，不是数据丢失）

auto_loop 探针轮必须把探针配置写 asset（Unity 批跑只读 asset）→ asset 临时变探针 →
DB 前端按 asset 配置匹配不上 → 显示白。**无法避免**（除非大改 Unity 批跑支持外部配置）。
但**数据不会丢**，四层保障：
1. `assets_backup/{lv}.asset.bak`（write_ddc 写入前自动备份）
2. 调优前手动快照 `project-state/pre_tune_backup_*/`（asset + db_entries.json）
3. DB entry 原样保留（reimport entry 未删）
4. Excel 入库记录（手动挑配置记录.xlsx）

调优完：合格 → reimport 新配置恢复绿；不合适 → 用 .bak 恢复 asset 立即恢复匹配。
