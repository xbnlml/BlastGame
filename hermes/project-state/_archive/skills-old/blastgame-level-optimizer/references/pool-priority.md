# 数据池优先级规则

## 公式

```
priority = gameTier × 5 + sourceRank

gameTier:  0 = ≥400, 1 = 300-399, 2 = 200-299, 3 = <200
sourceRank: 0 = bot, 1 = summary, 2 = phase0, 3 = phase2, 4 = phase1
```

## 完全表

| priority | 来源 | 局数 |
|----------|------|------|
| **0** | bot | ≥400 |
| **1** | summary | ≥400 |
| **2** | phase0 | ≥400 |
| **3** | phase2 | ≥400 |
| **4** | phase1 | ≥400 |
| **5** | bot | 300-399 |
| **6** | summary | 300-399 |
| **7** | phase0 | 300-399 |
| **8** | phase2 | 300-399 |
| **9** | phase1 | 300-399 |
| **10** | bot | 200-299 |
| **11** | summary | 200-299 |
| **12** | phase0 | 200-299 |
| **13** | phase2 | 200-299 |
| **14** | phase1 | 200-299 |
| **15** | bot | <200 |
| **16** | summary | <200 |
| **17** | phase0 | <200 |
| **18** | phase2 | <200 |
| **19** | phase1 | <200 |

## 关键原则

1. **数字越小越可靠**。`dedup_records` 保留 `_source_penalty` 最小的记录。
2. **同配置不同来源** → 保留可靠的。例如同 (sd,sc,ratios,of) 有 summary400 和 phase2，保留 summary400 (pen=1 < pen=13)。
3. **同优先级取更新** → 同 penalty 时保留 `created_at` 更新的。
4. **bot > summary > phase** → 同局数档位内，bot 优先。
5. **`find_best_monotonic` 不要预过滤数据源** — 传全部 `recs`，算法自己用 `_source_penalty` 排。人为选择"有 phase2 就用 phase2"会导致 summary 数据被丢弃。

## 实现位置

- `tools/data/pool.py` — `_source_penalty()` 函数、`dedup_records()` 去重
- `tools/data/adapters/bot_csv.py` — bot 数据读取
- `tools/data/adapters/opt_csv.py` — summary/phase 数据读取
- `tools/get_level_pool.py` — 旧版去重也已同步用 `_source_penalty`
