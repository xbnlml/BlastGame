# Batch Mode 故障排查

## 症状：CSV 文件为空（0 数据行）

CSV 有 header 无数据，totalElapsedSec < 1ms，所有 winkate=1.0。

### 排查流程

1. m_Name 是否=关卡号？ grep m_Name: {asset}。否 / 关卡身份不对 / bot 跑错关（例：59.asset 中 m_Name=51，一直玩 51 关）
2. customCellDrawingListV2 缩进？ grep customCellDrawingListV2: {asset}。开头无空格(缩进=0) / Unity 读不到 myStage。正确：与 DynamicDifficultyConfigs 同级缩进（4空格）
3. difficultyLevel 是否正确？ grep difficultyLevel: {asset}。normal=0, hard=1, superhard=2。SuperHard设成0 / 游戏自动秒杀全赢
4. 5档完整？ python -c "from tools.asset_patcher import read_ddc; print(len(read_ddc(LV)))"。>5档/重复写入/YAML尾部垃圾。bot 读不到正确配置。
5. 日志检查 cat campaign-attempts-*.csv。clearedCellCount=0 / 读了关卡但没跑。timeSec=0 / 瞬间完成。tier=1 for all / 所有档位用了空参数。

### 常见根因

| 症状 | 根因 | 修复 |
|------|------|------|
| 全 100% 秒杀 | ccV2 缩进=0 或 difficultyLevel=0 | 修正缩进，设正确 difficultyLevel |
| 全 100% 但 timeSec>0 | 配置太易（新 bot 强） | 换更难参数 |
| 多关合并为 1 行（winCount=400/关数） | 新 bot 分支合并批次 | 属游戏代码变更 |

## 症状：batch mode 不启动

1. tasklist /FI /Unity.exe — 编辑器在跑？不能同时运行
2. Access token unavailable — 警告无害，不影响运行
3. License failed/Fatal Error — 有另一个 Unity 实例占 license
