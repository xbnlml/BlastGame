# 批后自动分析 — post_batch_review.py

批跑完成后快速对比新数据 vs 之前最佳组合，检测配置偏差。

## 用法

```bash
# 分析最新 batch
python tools/post_batch_review.py --full

# 指定 batch
python tools/post_batch_review.py --batch "82_98-2026-07-17T18-11-36"

# 只看某几关
python tools/post_batch_review.py 82,98

# 组合参数
python tools/post_batch_review.py 82,98 --batch "82_98-2026-07-17T18-11-36" --full
```

## 输出解读

```
L82 (Normal) — 目标 90/90/75/60/60
  批次数据:
     档    WR     sd  ratios               of  来源  死亡
    T1   59.2%  25   1,10,1,1,1         0.5  bot   ⚠️ 预期是 sd=0 ratios=1,1,1,1,1 of=0.01
    T2   81.2%  0    1,1,1,10,10       0.01 bot
    T3   77.5%  20   1,9,1,1,1         0.5  bot
    T4   59.2%  25   1,10,1,1,1        0.5  bot
  之前 best:
    T1: WR=81.2% sd=1 ratios=1,1,1,1,1 of=0.5
```

`⚠️ 预期是...` 标记表示 batch 中实际运行的配置与 `probe_configs.json` 不一致（即 tier 映射 bug）。

## 工作流集成

批C（裁定）第 1 步：
```bash
python tools/post_batch_review.py --full
```
然后 `dump_level_pools` → `find_best_combo` → 判定。
