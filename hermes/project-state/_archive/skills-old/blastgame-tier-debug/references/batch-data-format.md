# 批量 Bot 数据格式（101-200 关经验）

## 两种目录结构

`read_bot_attempts` 支持两种 bot 数据目录结构：

### Flat 格式（L101-200 使用）

```
telemetry/bot/
  L101-200-T1-{timestamp}.batch-range/
    campaign-attempts-L101-200-T1.csv    # 所有 100 关的 attempt 数据
    campaign-summary-L101-200-T1.csv     # 所有 100 关的 summary 数据
  L101-200-T2-{timestamp}.batch-range/
    ...
```

特点：
- 每档一个目录，覆盖所有关卡
- CSV 列名：`level` （不是 `gameLevel`）
- 100 关共用一个 CSV 文件
- tier 从文件名 `T{tier}-` 提取

### Nested 格式（L51-100 使用）

```
telemetry/bot/
  51-52-{timestamp}/
    L51-52-T1-{timestamp}.batch-range/
      campaign-attempts-L51-52-T1.csv
      campaign-summary-L51-52-T1.csv
    L51-52-T3-{timestamp}.batch-range/
      ...
```

特点：
- 每批关一个外层目录，里面每档一个子目录
- CSV 文件名为 `campaign-*-{range}-T{tier}.csv`
- 支持同目录下多关合并

## 读取注意事项

- 两种格式 `read_bot_attempts` 都自动识别（`os.walk` 递归查找）
- `level` 列是关键：Nested 用 `level`，Flat 也用 `level`
- `tier` 从文件路径中 `T{tier}-` 模式提取
- 更新 `get_level_range()` 后重建池子即可

## 入池验证

重建池子后抽样检查：
```python
from tools.data import pool
recs = pool.get_preferred_records(str(LV))
bot = [r for r in recs if r.get('source') == 'bot']
t1 = [r for r in bot if str(r.get('tier','')).startswith('T1')]
t1[0]  # 应有 400 局
```
