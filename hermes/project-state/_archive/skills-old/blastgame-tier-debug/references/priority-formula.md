# 数据优先级公式

## 核心原则

**局数优先，同局数再按来源比。**

## `_source_penalty` 公式

```python
tier = 0 if games >= 400 else (1 if games >= 300 else (2 if games >= 200 else 3))
rank = {'bot': 0, 'summary': 1, 'phase0': 2, 'phase2': 3, 'phase1': 4}.get(source, 5)
return tier * 5 + rank
```

## 罚分速查

| 数据 | 局数 | 来源 | 罚分 |
|------|------|------|------|
| bot | ≥400 | bot | 0×5+0 = **0** |
| summary | ≥400 | summary | 0×5+1 = **1** |
| phase0 | 300-399 | phase0 | 1×5+2 = **7** |
| bot | 300-399 | bot | 1×5+0 = **5** |
| phase2 | 200-299 | phase2 | 2×5+3 = **13** |
| bot | 200-299 | bot | 2×5+0 = **10** |
| phase1 | <200 | phase1 | 3×5+4 = **19** |

## 组合品质分中的权重

`source_score` 在 `find_best_monotonic` 的品质公式中权重为 **×0.3**（2026-07-20 修正），防止局数优势压倒 WR 差距：

```python
q = target_score + source_score * 0.3 + gap_score + death_score
```

同等 WR 条件下，bot 400 局才会优于 bot 270 局。3.5pp 的 WR 差距不会被来源优势完全逆转。

## 应用位置

`_source_penalty` 在所有决策点统一使用：
1. `pool.py:get_preferred_records` — 去重排序
2. `pool.py:save_assist_data` — 辅助数据去重
3. `pool.py:_bucket` — 窗口排序（同 WR 距离时用罚分作为第二排序键）
4. `pool.py:find_best_monotonic` — 组合质量分含 `source_score`
5. `get_level_pool.py:dedup_by_priority` — 池子构建时去重

⚠️ `_priority` 字段（在 `get_level_pool.py` 中设置）是冗余 metadata，**不影响任何决策**。实际排序始终依赖 `_source_penalty`。
