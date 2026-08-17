# 参数经验知识库 — param_knowledge.py

**文件**: `tools/param_knowledge.py`

## 用途

设计探针前，先查参数经验表，避免盲目打方向。从所有关 2947 条完整数据（含 phase1/phase2）学习参数→WR 规律。

## 用法

```bash
# 查看某关的缺口方向 + 经验表推荐参数
python tools/param_knowledge.py 153

# 查看所有关出现过哪些 ratios 值（不只是 10 和 1）
python tools/param_knowledge.py --ratios-pool

# 查看完整经验表摘要
python tools/param_knowledge.py
```

## 原理

1. 遍历所有关的完整数据（dedup_records，含 phase1/phase2/reference）
2. 按 (难度, ratios_pattern, sd_档次) 分组统计 WR 分布
3. 产出经验表：每种 ratios × sd 在 Normal/Hard/SuperHard 下通常出多少 WR
4. 设计 agent 查表反推：要 X% WR → 推荐 ratios + sd 范围

## 关键发现

- ratios 值不止 10 和 1：0(502次), 2(385次), 3(173次), 4(150次), 5(523次), 6(72次), 7(79次), 8(103次), 9(140次)
- 中间值（2~9）是调节前/后/中段权重的关键——不要只写 10 和 1
- 同 pattern 内 sd 趋势才可比（跨 pattern 比 sd 无意义）
- 统计是相关不是因果，试错仍是必须的，只能让方向更准

## 探针设计建议

1. 先跑 `param_knowledge.py <lv>` 看缺口方向
2. 根据目标 WR 查经验表，找到推荐 ratios+sd 范围
3. 在该范围内选 5 个不同配置（不同 ratios 模式）
4. 结合本关已有数据验证方向是否合理
5. 5 槽全用上，一次批跑拿 5 个新数据点