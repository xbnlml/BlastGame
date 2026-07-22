# Asset 格式调试

## 三条硬性规则

1. `DynamicDifficultyConfigs:` 和第一个 `customCellDrawingListV2:` 必须在**同一缩进级**
2. `m_Name: XX` 必须等于关卡号（否则 bot 跑错关）  
3. `difficultyLevel: N` 匹配难度（normal=0, hard=1, superhard=2）

## 正确格式

```
    DynamicDifficultyConfigs:        ← 4 空格
    - StartDifficulty: 5              ← 4 空格（跟 DynamicDifficultyConfigs 同级）
      ShuffleSplitCount: 5            ← 6 空格
      ShuffleSplitRatios: 1,1,1,1,1
      ShuffleOverflowFactor: 0.5
    - StartDifficulty: 5
      ...
    customCellDrawingListV2:          ← 4 空格（与 dd 同级）
    - Enabled: 1
      Value: 17
      SpecialFlags: 0
      Collectable: 0
    ...
  myStage:
    width: 4
    height: 10
    requiredCount: 20
    customCellDrawingListV2:          ← myStage 内部第二个（4 空格）
    - Enabled: 1
```

## 诊断命令

```bash
# 1. 缩进检查 — ccV2 不能行首 0 空格
grep -n "customCellDrawingListV2:" {asset} | head -5

# 2. 关卡名
grep "m_Name:" {asset}   # 必须=关卡号

# 3. difficultyLevel
grep "difficultyLevel:" {asset}  # 0/1/2

# 4. 5 档完整性
python -c "from tools.asset_patcher import read_ddc; print(len(read_ddc(LV)), 'tiers')"

# 5. 完整缩进展示
sed -n '/DynamicDifficultyConfigs:/,/customCellDrawingListV2:/p' {asset} | head -20
```

## 故障模式速查

| 症状 | CSV 现象 | 根因 | 修复 |
|------|---------|------|------|
| 全秒杀 | `timeSec=0, clearedCellCount=0, 100% win` | **ccV2 缩进=0 → myStage 读不到 → Unity 不加载牌面** | `sed -i '0,/^customCellDrawingListV2:/s//    customCellDrawingListV2:/'` |
| 跑错关 | `level=51` 不是目标关 | `m_Name` 还是 51 | `sed -i 's/m_Name: 51/m_Name: 59/'` |
| 全简单 | `DifficultyLevel=0` 应是 2 | `difficultyLevel` 值不对 | `sed -i 's/difficultyLevel: 0/difficultyLevel: 2/'` |
| 空 CSV | log 中 key 参数 `sd=0/split=0/ratios=""` | YAML 缩进错或 >5 档 | 从 git 恢复后再 `write_ddc` |
| >5 档 | `read_ddc` 返回 10/8/7 等 | 多次 write_ddc 未清理 | git checkout → write_ddc |
| 批量全 100% | 6 关 × 400 局 = 2400 行，level=51 | ccV2 缩进错误**影响所有关** | 同上修复 |

## 根因链路（这次教训）

```
customCellDrawingListV2: 缩进=0
  → Unity YAML 解析失败，customCellDrawingListV2 层次错乱
  → myStage 数据不可达
  → 游戏无牌面信息，0 目标格
  → 所有游戏瞬间完成（timeSec=0, clearedCellCount=0）
  → 100% 胜率
```

## 修复方法

### 方法 1：从 git 恢复（保留关卡参数）← 首选

```bash
cd $BLASTGAME_REPO
git checkout -- Assets/.../test/59.asset
python -c "
from tools.asset_patcher import write_ddc; import json
with open('D:/download/Hermes/tools/probe_configs.json') as f: cfg=json.load(f)
c=cfg['59']; tiers=[c['T%d'%i] for i in range(1,6)]
write_ddc(59,tiers)
"
```

**绝不能拿别的关的 asset 做模板整体替换。** 每个关有独立的 m_Name、myStage、myStack、牌面参数。做整体模板替换会丢失所有关卡特有参数。

### 方法 2：手动修缩进

```bash
sed -i '0,/^customCellDrawingListV2:/{s/^customCellDrawingListV2:/    customCellDrawingListV2:/}' {asset}
```

### write_ddc 的缩进自动修正

v5.3+ 的 `write_ddc` 在写入后自动修正 `customCellDrawingListV2:` 的缩进（与 `DynamicDifficultyConfigs:` 对齐）。但如果文件有多余 tier 块（>5 档），`verify_integrity` 会拒绝写入。此时先用 git 恢复原文件再 `write_ddc`。

## 常见修复误区

| 错误做法 | 后果 |
|---------|------|
| 用 51.asset 做模板复制到其他关 | 所有关 m_Name 变成 51，myStage/myStack 参数被替换 |
| `git checkout` 后不修缩进直接跑 | 缩进仍是错的，bot 全秒杀 |
| 直接用 sed 替换 tiers 段 | 缩进可能写错，且无法处理 sc/ratios 匹配 |
| `write_ddc` 多次调用同一关 | 文件累积多组 tier 块 → 读成 >5 档 |
