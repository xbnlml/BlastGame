# 判定规则参考（judge_level.py 权威实现）

> **单一真理源：`judge_level.check_judgment()` 是判定权威实现。本文档描述其规则，供人类参考。**

## ② 合格判定

### Normal
- T1→T3 ≥ 15pp, T3→T5 ≥ 15pp
- T3 ≥ 60%（硬性）

### Hard
- 各相邻档差 ≥ 10pp
- T3 ∈ [30%, 60%]

### SuperHard
- 各相邻档差 ≥ 10pp
- T3 ≤ 50%

### 偏离 ≤2pp 直接合格

## ③ 硬性违规（任一即不合格）

- 任意相邻档差 < 5%（Normal T1=T2/T4=T5 除外）
- 倒挂超 1%（低档 WR > 高档 WR）
- 任意档 WR < 5%
- Normal T3 < 60%

## ⑤ 结果分级 + 6轮上限

| 结果 | 操作 |
|------|------|
| ✅ 合格 | 入库 |
| ⚠️ 接近（偏离≤2pp 或 WR≤5pp） | 标记 |
| ❌ 不合格 | 下一轮 |
| ❌ 6轮仍不合格 | 改关卡 |

轮次追踪：`project-state/_rounds.json`（`judge_level.judge_with_rounds()` 管理）
