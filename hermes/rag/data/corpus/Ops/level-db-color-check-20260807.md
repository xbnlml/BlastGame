# 关卡数据库 test.json 结构 + 红/白/绿判定（2026-08-07）

> 场景：用户问"关卡数据库哪些关是白/红的，能否用新数据变绿（减少红色）"。
> 读取 `LevelDatabase/Run/test.json` 判定每关 DB 现状。

## test.json 真实结构（关键，别猜）

**每关 `levels[<lv>].entries` 是"单档 entry"列表，不是五档组合。** 每条 entry：
- `dealConfig`（单档配置：startDifficulty / shuffleSplitCount / shuffleSplitRatios / shuffleOverflowFactor）
- `winRate`（该档实测胜率）
- `sourceTierLabels`（如 `["T3"]`，标档位）
- `fingerprint` / `boardFingerprint` / `dealFingerprint`
- **没有 5 档 `tierConfigs` 数组**（101-150/151-200 全部 entry 都是单档结构，已确认）

## ⚠️ compare_level_db.py 对单档 DB 结构不适用（工具限制）

`compare_level_db.py` 的"活动 entry"判定找的是 `tierConfigs`（5 档数组）的 entry，但真实 DB 是单档 `dealConfig` → **它对所有关都报"无活动 entry"（白色），不可靠**（包括已入库的 165/182 也报无）。用它判断 DB 红/白/绿会全判成白，是错的。

## 正确判定红/白/绿（相对目标）

按"每关 asset 的 5 档配置，分别匹配 DB 里该档配置相同的 entry，取其 winRate"：

```python
def match_cfg(tc, a):  # tc=entry.dealConfig, a=asset 该档 {sd,sc,ratios,of}
    return (int(tc['startDifficulty'])==int(a['sd']) and
            int(tc['shuffleSplitCount'])==int(a['sc']) and
            norm_ratios(tc['shuffleSplitRatios'])==norm_ratios(a['ratios']) and
            abs(float(tc['shuffleOverflowFactor'])-float(a['of']))<1e-6)
# 每档：遍历该关所有 entry，找 dealConfig 匹配 asset[i] 的，取 winRate
```

各档 winRate×100 相对目标（excel_target.read_targets() 的 `tiers`）：
- 偏差 ≤10pp → 🟢绿
- 10 < 偏差 ≤15 → 🟡黄
- 偏差 >15 → 🔴红
- 该档无匹配 entry → ⬜白

## "哪些关能用新数据变绿"的判断

只调红/白/黄关，看该关**新多档位批次**（`telemetry/multi-tier-opt/<lv>-<ts>/`）有没有能贴近目标的可靠配置：
- **summary.csv**（phase0/phase3，已验证局数）→ ✅ 可直接参考写 DB
- **phase2_candidates.csv** → 探针级，可参考
- **phase1_raw.csv** → 只有覆盖率，不能直接入库
- 若 phase1 最高才 45-67%（如 119/120/138/144 对 85 目标），说明**牌面过难、数据覆盖不到目标段，需改关卡而非用数据改善 DB**。

## 教训
- 判断 DB 红/白/绿前，先确认 DB 是单档还是五档 entry 结构，别套用 `tierConfigs` 假设。
- 用户强调的"减少红色 = 增加绿色"指**相对目标**的偏差，不是 DB vs 池子对比。