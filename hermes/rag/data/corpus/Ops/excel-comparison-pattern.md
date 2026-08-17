# Excel vs Bot 数据对比模式

## 数据源

- Excel: `C:/Users/Administrator/Documents/BlastGame/Doc/手动挑配置记录.xlsx` — 入库记录
- 外部 Bot: `C:/Users/Administrator/Documents/BlastGame/telemetry/bot/101-200-2026-07-20T17-34-01/` — 每档 400 局

## 对比步骤

1. 读取 Excel 每关每档的配置（sd/sc/ratios/of）和 WR
2. 读取外部 Bot 数据的对应配置和 WR
3. 归一化比较：of 为空 = 0.0，WR=1.0 = 100%
4. 分类：
   - 配置一致 + WR 差<2pp → 可直接入库
   - 配置一致 + WR 差 5-10pp → 需关注
   - 配置一致 + WR 差≥10pp → Excel WR 需更新
   - 配置不一致 → 非同一套配置

## 关键规则

- Excel 不直接写入外部数据，只做参考对比
- 外部数据来源不自行判断新旧，客观对比
- 101-200 外部 bot 数据 vs Excel 配置一致率 94%（81 关全 5 档一致）