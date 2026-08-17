# auto_loop tiers 变量污染 → 6 轮探针空转（2026-08-05 根因）

## 症状
- auto_loop 跑 L154/165/182/198，6 轮全部空转：每轮 combo quality 完全恒定（47.9/57.3/177.0/104.4）、胜率/判定每轮一字不差。
- 关卡数据库里这些关仍是白关（无匹配活动 entry / 无数据）。
- auto-log 里 `Submitting Unity batch` 的 `--tiers` 参数是 **dict 字面量** `{'sd':20,...},{'sd':40,...}`，而不是 `1,2,3,4,5`。

## 根因
`auto_loop.py` Phase 5 PASSED 分支（判合格/接近后记录最优组合那段）：
```python
tiers = [{'sd': int(best[i]['sd']), 'sc': int(best[i]['sc']),
          'ratios': str(best[i]['ratios']), 'of': float(best[i]['of'])}
         for i in idx]
```
把**全局 `tiers` 变量**从 `[1,2,3,4,5]` 覆盖成最优组合 dict。只要任一关在某轮通过（本案例 ROUND 2 L162 入库），从下一轮起：
```python
phase_submit_batch(log, current_pending, tiers, ...)   # tiers 已是 dict
```
`phase_submit_batch` 里 `','.join(str(t) for t in tiers)` 拼出 dict 字面量传 `--tiers`，Unity 跑的是**同一组最优组合**而非轮次新探针 → 数据永远不变。

## 关键特征：ROUND 1-2 正常、ROUND 3-6 突变
ROUND 1-2 传 `1,2,3,4,5`（正常），ROUND 3-6 突变 dict。因为污染发生在 **ROUND 2 结束时**（L162 PASSED 触发 743 行）。若一开始就错，会是全程 dict；"中途突变"强烈指向某关在某轮通过后触发的跨轮污染。

## 修复
PASSED 分支用局部变量 `best_tiers`，不覆盖全局 `tiers`；后续引用 `best_tiers` 同步改。

## 排查模式（通用）
多轮探针数据/判定完全不变时：
1. 先 diff 各轮 `Submitting Unity batch` 的 `--tiers` 参数是否一致/是否被污染成 dict。
2. 若 ROUND 走一半突变，找"哪关在哪轮通过" —— 通过分支里是否改写共享变量。
3. 探针"设计了但没效果"≠没设计 —— 先查 auto-log 实际提交给 Unity 的参数，再怀疑探针本身。

---

# 白关（关卡数据库无匹配数据）诊断：必须用官方 node 函数

**白关定义**：`resolveRunForLevel` 返回 `aligned=false`，reason「关卡 tier 配置已变更，无匹配批跑」= asset 当前配置在 DB 里无 fingerprint 匹配 entry。

**正确诊断链**：
1. `node --input-type=module` 调 `readAssetTierSnapshot(buildLevelAssetPath(generatedRoot, folder, lv))` 读 asset 配置
2. `resolveRunForLevel(runStore, lv, tiers)` 判 aligned（runSummaryImport.mjs，官方逻辑 = fingerprint 匹配 + 逐档 `tierConfigsEqual`）
3. aligned=false 即白关

**别用 Python 自复现 fingerprint**（坑 93）：normalize 细节（of 精度/字段序）有偏差，L200 自算 927b626c 全错，DB 实际 entry 是 912677f6。

**白关 ≠ 池子没数据**：read_ddc 与官方 readAssetTierSnapshot 读同一文件（`Generated_enum/test/{grp}/{lv}.asset`）结果应一致；白关说明 asset 当前配置在 DB 无对应 entry（通常是关卡被改/探针配置未跑完入库）。若两工具读同一文件不一致 → 先怀疑 asset 被改（查 `assets_backup/{lv}.asset.latest.bak` mtime）。

---

# compare_imported.py 单位防御方向写反（已修）

坑 115 说 Excel 胜率列是小数（0.8=80%），但 compare_imported.py 曾写 `if abs(v)>2: v/=100`——把已是小数的 0.8 当百分数保留，导致「变化 89.9pp / 判定不合格」全假象。

**正确方向**：Excel 值 `≤2` → `×100` 转百分数（0.8→80）；`>2` 视为已是百分数保留；`new_wrs` 来自池子本就是百分数。

**通用教训**：比较 Excel vs 池子/DB 时先确认两侧单位（小数 vs 百分数），写脚本的防御逻辑方向要对。

---

# 底层阻塞：Unity 编译错误（CS0246）→ 探针跑不出去 → 白关

**症状**：submit_batch_unity 11 秒就「Unity batch completed」+ `=== DONE ===`，但 telemetry 无新批次目录、无 Unity.exe 进程。

**根因**：Unity 脚本编译失败（`Scripts have compiler errors` + `CS0246: The type or namespace name X could not be found`），batch 立即 exit 1，auto_loop 误判「completed」。

**排查**：手动 `python submit_batch_unity.py <lv> --tiers 1 --games 2 --yes --skip-agent-pipeline` 看真实 Unity 输出；`rg -l "类型名" Assets/` 确认类型是否全项目缺失（只有引用处 = 定义丢失）。2026-08-05 案例：`EventCommonBtnHaptic` 只在 GameHapticManager.cs 被引用、全 Assets 无定义（项目代码问题，用户修）。

**注意**：这是临时编译错误，非工具缺陷，修好即可，别把它当「Unity 不能用」硬化成约束。