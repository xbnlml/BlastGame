# CSV 读取与监控 — 关键教训

## 🔍 事故：L67 `cut -d,` 全盘误读 (2026-07-01)

### 现象
用 `cut -d, -f7 campaign-summary-L67-T1.csv` 读 CSV，得到 T1=27.6%。
实际 T1=**85.5%**。差了 3 倍。

### 根因
CSV 的 `failBucketDistribution` 列是一个**引号包裹的逗号分隔数组**：
```
test,67,0,"0,0.028,0.009,0.17,0.208,...",294,106,0.735000
```

`cut -d,` **不认引号**，把分布里的 `0.17` 当成第 7 列。实际 winkate 是最后一个字段。

### 铁律
**永远用 Python csv 模块或 pandas 读 CSV。禁止用 cut/awk/sed。**

```python
# ✅ 正确
import csv
with open('campaign-summary-*.csv') as f:
    for row in csv.reader(f):
        wr = float(row[-1])  # winkate 是最后一列

# ✅ 或者 pandas
import pandas as pd
df = pd.read_csv('campaign-summary-*.csv')
print(df[['level', 'winkate']])
```

## 批次完成检测（monitor_bot.py）

脚本在 `~/.hermes/scripts/monitor_bot.py`，核心逻辑：

1. 记下 `BuildLogs/auto-batch-last-export.txt` 的 mtime
2. 每秒检查一次
3. mtime 变了 → 批次完成
4. 自动关弹窗、读结果、打印报告

启动：`terminal(background=true)` 中运行 `python ~/.hermes/scripts/monitor_bot.py`，加上 `notify_on_complete=true`。
