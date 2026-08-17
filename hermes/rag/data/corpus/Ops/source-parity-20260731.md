# 数据源同级新语义（2026-07-31 用户定稿）+ L168/L160 案例

## 用户原话（必须逐字遵守）

> "bot summary phase0都是几乎同级，只是冲突的时候才按先后顺序选，这种新数据在同级情况下肯定优先用新数据啊"

## 语义

| 来源 | 旧语义 | 新语义 |
|---|---|---|
| bot / summary / phase0 | bot(0) < summary(1) < phase0(2) 分档 | **同级**（rank 全 0），冲突时按先后顺序选，**新数据优先** |
| phase2 / phase1 | 3 / 4 | 仍罚（1 / 2），且不可直接入库（filter_verified 铁则不变） |
| 局数分档 | ≥400:0 / 300-399:1 / 200-299:2 / <200:3 | 保留不变 |

## 代码实现（tools/data/pool.py）

```python
def _source_penalty(source, games):
    tier = 0 if games >= 400 else (1 if games >= 300 else (2 if games >= 200 else 3))
    rank = {'bot': 0, 'summary': 0, 'phase0': 0, 'phase2': 1, 'phase1': 2}.get(source, 3)
    return tier * 5 + rank

# dedup_records: 同级（penalty 相等）时按 created_at 取新
# _bucket: 先按 created_at 降序，再用稳定排序 (abs(wr-target), penalty) → 同级内新数据在前
```

**save_bot_data / save_assist_data 绝不能 cross-dedup**（写入时删另一文件同配置）——旧逻辑"bot 永远优先"会丢掉更新的 summary 数据。只做文件内按 created_at 去重，跨文件去重统一交给 dedup_records。

## L168 案例（用户质疑"你看的数据是最新的吗？"）

**症状**：展示的 L168 最优组合（49.2/36.0/25.8/17.5/17.5）与用户看的 151-170 新批次 summary（48.2/35.4/33.3/22.5/14.0）不一致。

**根因链**：
1. 新批次 optimizer 的 T3/T4/T5 **复用了旧 bot 同配置**（sd14/0,1,1,1,1,0、sd30/4,5,1、sd34/0,1,6,4）但跑出新 WR（33.3/22.5/14.0 vs 旧 bot 36.0/23.8/17.5）
2. 旧 `save_assist_data` 有 cross-dedup：`跳过 bot 已有的同配置` → 新 summary 的 T3/T4/T5 记录**在 dump 时就被丢弃**，assist.json 只剩 2 条（T1/T2 的新配置）
3. `save_bot_data` 也有反向 cross-dedup：写入 bot 时删除 assist 同配置

**修复**：两个 save 函数去掉 cross-dedup，只做文件内按 created_at 去重；跨文件去重统一由 `dedup_records` 处理（同级取新）。修复后 L168 池子 7 条全在（5 条新 summary + 旧 bot 中配置不同的 49.2/25.8）。

## L160 案例（修复后重查 → 判定翻转）

**症状**：修复后重查过渡期入库的 7 关（L151/157/160/161/163/164/169），L160 最优组合从 `84.1/84.1/65.6/48.5/48.5`（接近，已入库）变成 `84.1/84.1/70.0/51.2/51.2`（**不合格**，T1-T3=14.1<20）。

**根因**：65.6/48.5 是 **7-29 旧 bot 批次**（`telemetry/bot/51-200-2026-07-29T10-50-22`）同配置记录；70.0/51.2 是 **151-170 新 summary 批次**（7-30）同配置记录。修复前池子只有旧 bot → 判定"接近"入库；修复后同级取新 → 新 summary 胜出 → 判定变不合格。

**关键教训**：
1. **入库判定必须基于最新池子**——同一配置多批次数据时，判定结果随数据源变化（接近↔不合格翻转）
2. **asset 四元组可能没变**（L160 写入的 sd=39/sd=33 与新旧数据都一致），但 WR 判定变了——配置有效 ≠ 判定有效
3. 修复数据源语义后，**必须重查所有过渡期入库的关卡判定**，向用户展示两种数据源视角（旧 bot vs 新 summary），由用户决定撤销入库还是保留

## 验证脚本模式

```python
# 同级验证
assert _source_penalty('bot',400) == _source_penalty('summary',400) == _source_penalty('phase0',400) == 0
# dedup 同级取新
recs = [旧bot记录, 新summary记录(同配置)]
d = dedup_records(recs)
assert d[0]['source'] == 'summary' and d[0]['wr'] == 新值
# save 互不删除
save_bot_data(lv, [...]); save_assist_data(lv, [同配置新summary])
assert len(load_bot_data(lv)) == 1 and len(load_assist_data(lv)) == 1
```
