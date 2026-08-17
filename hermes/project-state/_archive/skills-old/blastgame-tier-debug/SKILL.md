---
name: blastgame-tier-debug
description: "BlastGame tier 映射调试、Phase2 CSV 列偏移修复、Unity asset 缓存问题排查"
version: 1.0.0
author: Hermes Agent
platforms: [windows]
metadata:
  hermes:
    tags: [blastgame, debugging, tier-mapping, asset-cache]
    related_skills: [blastgame-level-optimizer]
---

# BlastGame Tier 映射 & Asset 调试

## 适用场景

Bot 批跑输出中，T1 读到的参数（sd/sc/ratios/of）与预期不一致，或者多档数据间的参数值异常（如 T1 的配置等于 T4/T5）。

## 排查流程

### 第1步：确认 asset 写入正确

```bash
python3 -c "
from tools.asset_patcher import read_ddc
result = read_ddc(LV)
for i, t in enumerate(result):
    print(f'Slot {i}: sd={t}' if isinstance(t, dict) else f'Slot {i}: {t}')
"
```

预期：Slot 0-4 依次为 T1 到 T5 的探针配置。

### 第2步：确认 device 文件格式正确

Python 工具只写 `test/` 下的 asset。`funnel_b/` 是竞品关卡数据，和 `test/` 不是一套东西，不比较、不引用、不写入。

### 误判记录：T1 读 slot 4 是假警报（2026-07-19 纠正）

**现象（假）：** Unity batch mode 中 T1 读取 asset slot 4（T5 位置）而非 slot 0。依据是 `Debug.Log("[TierMap]")` 只输出 tier=3/4/5，不输出 tier=1/2。

**真相：** `ResolveTierDifficultyConfig` 有两条调用路径——Gameplay 路径和预读取路径。Debug.Log 只在预读取路径中出现（该路径对 tier=1/2 提前返回不触发日志）。**实际游戏运行时 T1 读取正确**，summary CSV 中 T1 的 sd 值一直正确。无 tier 映射 bug。

**教训：** Debug.Log 缺失 ≠ bug。先确认代码路径再下结论。summary CSV 数据是真相——配置在 CSV 中的值就是实际游戏用的值。

**相关：** 此假警报导致不必要的 Python 侧 workaround（slot 4 复制 T1 配置），workaround 反而让 T5 读到了 T1 的配置。已全部回滚。

### 过时方案（已废弃）
以下方案曾经尝试但无效或不可行：
- `AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate)` — 无法保证 Unity 内存中 ScriptableObject 实例重新加载。实测添加后在 `BlastBotJenkinsBatchEntry.RunFromCommandLine`、`BlastWorkbenchWindow.Bot.cs`、`BlastBotCampaignRunner.ResolveEffectiveDifficultyConfig` 三处调用均无效。
- 清 Library/Bee/ArtifactDB 缓存 — 强制 Unity 重编译和重导入后，T1 仍读 slot 4。
- 加 C# `ResolveTierDifficultyConfig` null-fallback 逻辑 — 加了代码但 Unity 不重编译（旧 dll 缓存）。而且修改 C# 文件本身是红线操作。
- 写 `$BLASTGAME_REPO` 下的文件（.cs、.asset、Library、Temp）

### 第3步：确认 asset 读回正确

在 `BlastDynamicDifficultyPureLogic.ResolveTierDifficultyConfig` 返回前加：

```csharp
Debug.Log(\$"[TierMap] tier={resolvedTier} idx={tierIndex}/{configs.Count} sd={tierConfig.StartDifficulty} sc={tierConfig.ShuffleSplitCount} r={tierConfig.ShuffleSplitRatios} of={tierConfig.ShuffleOverflowFactor}");
```

同步在 `submit_batch_unity.py` 的过滤关键字中加 `'TierMap'`。

提交小批量跑（--games 3）查看日志输出。

## 关键参数理解

### Normal 低 sd 陷阱（2026-07-19 教训）

**sd=0/1 的 Normal 关，棋盘基本不洗牌。** Ratios（洗牌压力分布）和 of（溢出累积）只在 shuffle 发生时才有作用对象。当起始难度极低时，大多数局在初始牌面就已结束，后期 shuffle 不触发。

**表现：**
- T1 sd=0/1 时，换 ratios（前重/中重/后重）WR 不变
- T1 sd=0/1 时，调 of（0.01→1.0）WR 不变
- 死亡分布集中在后期 80-90%——实际是初始牌面决定了生死

**结论：**
- sd=0/1 Normal 下不要浪费探针槽测 ratios/of 变体
- T1 达不到目标时根因是初始牌面太硬，不是参数不行
- 直接标记改关卡，不迭代

**反面案例（L82）：** T1=78.5% 天花板，sd=1 下测 9 组 ratios/of 全 78.5%。死亡 91% 后期。纯浪费轮次。

### 严禁修改 BlastGame 项目文件
绝不写 `$BLASTGAME_REPO` 下的任何文件（.cs、.asset、Library、Temp）。所有排查/修复限制在 Hermes 目录内。

### Phase2 CSV 列偏移

### 现象

`phase2_candidates.csv` 数据中 `StartDifficulty` 值异常（如全是 5），或 `ShuffleSplitCount` 列出现逗号分隔的值（实际是 ratios）。

### 根因

C# 导出时 `Phase2Appended` 列不输出数据，但表头存在。实际数据列比表头少 1 列，导致所有字段左移：

| 表头列 | 实际数据 |
|--------|---------|
| Phase2Appended | sd 的值 |
| StartDifficulty | sc 的值 |
| ShuffleSplitCount | ratios 的值 |
| ShuffleSplitRatios | of 的值 |
| ShuffleOverflowFactor | (无数据) |

### 检测方法

**不依赖字段值内容**（ratios 也可能不含逗号，sc=1 时 ratios 就是单个数字）。正确检测：**比较数据行和表头的列数**。

```python
header_cols = len(raw_lines[0].strip().split(','))
data_cols = len([v for v in row.values() if v is not None])
shifted = data_cols < header_cols
```

### 读数据

当 `shifted=True` 时：
- sd = row['Phase2Appended']
- sc = row['StartDifficulty']
- ratios = row['ShuffleSplitCount']
- of = row['ShuffleSplitRatios']

当 `shifted=False`（未来正确格式）：
- sd = row['StartDifficulty']
- sc = row['ShuffleSplitCount']
- ratios = row['ShuffleSplitRatios']
- of = row['ShuffleOverflowFactor']

此检测在 `get_level_pool.py` 的 `read_opt_data` 中实现，不依赖 Phase2Appended 是否有值。

### `read_ddc` YAML 解析注意事项

`asset_patcher.py` 的 `read_ddc()` 解析 Unity YAML 时，`- StartDifficulty: 1` 这种 key-value 在**同一行**的格式需要特殊处理——先解析 `- ` 后的内容，再处理后续缩进行。原代码只跑后续缩进行而跳过第一行，导致 StartDifficulty 永远读不到。

```python
# 正确解析:
if line.startswith('- '):
    content = line[2:].strip()  # "StartDifficulty: 1"
    if ':' in content:
        k, v = content.split(':', 1)
        # 解析第一行 key-value
    # 再继续解析后续缩进行
```

修复后实际使用中确认 YAML 的 `customCellDrawingListV2` 缩进问题也可能影响解析。write_ddc 写入后应自动修正。

### `_bucket` 窗口排序（2026-07-19 修复）

`pool.py:_bucket()` 的排序键原来只按 WR 距离：`abs(r['wr'] - target)`。同距离时低质量数据（phase2/phase1）可能挤掉高质量数据（bot/summary/phase0）。

修复后：`(abs(r['wr'] - target), _source_penalty(...))` — **同 WR 距离时，来源优先级高的记录优先入桶**，避免低质量数据占满窗口。

### `find_best_monotonic` 组合质量分

组合质量分 `q` = `target_score + source_score + gap_score + death_score`，其中 `source_score = sum(_source_penalty(r) for r in recs)`。所以即使低质量数据进入了桶，其更高的 `source_score` 也会在组合排序时被惩罚。

### phase0_prior.csv 数据缺失（2026-07-19 教训）

**`get_level_pool.py` 不读 phase0_prior.csv。** 该文件包含优化器阶段 0 的 300-400 局实际 bot 数据（列名 `PriorWinRate`）。

**为什么会被忽略：** `read_opt_data` 函数只处理 summary/phase2/phase1_raw。

**修复：** 在 `read_opt_data` 中加 phase0 读取，放入参考池（`source='phase0'`, `_priority=2`）。池子的 `_source_penalty` 函数已支持 phase0（penalty=2，介于 summary=1 和 phase2=3 之间）。

**`_priority` 对齐（2026-07-19 修复）：** `get_level_pool.py` 中 `_priority` 值和 `pool.py` 的 `_source_penalty` 已对齐一致：
| 来源 | _priority | _source_penalty |
|------|-----------|-----------------|
| bot≥400 | 0 | 0 |
| summary | 1 | 1 |
| phase0 | 2 | 2 |
| phase2 | 3 | 3 |
| phase1 | 4 | 4 |

**检查 optimizer 所有输出文件：** 查看 optimizer 数据时不要只查 summary 和 phase2。每个 optimizer 子目录下有：
- `phase0_prior.csv` — 初始估计（300-390 局实际 bot 数据）
- `phase1_raw.csv` — 阶段1 原始数据（100 局/配置）
- `phase1_reachability.csv` — 可达性分析
- `phase2_candidates.csv` — 阶段2 候选配置（200 局/配置）
- `sensitivity.csv` — 参数敏感度分析
- `detail.csv` — 各档最优结果
- `summary.csv` — 汇总

全查看后再下结论，不要只看一个文件就定论。

**每次调整 `get_level_pool.py` 后必须重建池子：**
```bash
rm -rf stage-data/{lv}
python tools/dump_level_pools.py
```

### `find_best_monotonic` 组合质量分

`q = target_score + source_score * 0.3 + gap_score + death_score`

- `source_score *= 0.3` 避免局数优势压倒 WR 差距（2026-07-20）
- `gap_score` 采用分层连续公式（见下）

### Gap 罚分公式（2026-07-20 定版）

```python
if g < 15: score += (15 - g) * 5     # 基本
if g < 10: score += (10 - g) * 10    # gap<10 额外加罚
```

| gap | 罚分 | 说明 |
|-----|------|------|
| 15pp | 0 | ✅ 达标 |
| 12pp | 15 | ≈ 各档离目标 5% |
| 10pp | 25 | 中等 |
| 8pp | 35+20=55 | 重 |
| 5pp | 50+50=100 | 很重 |

边界连续无跳变（g=10 时两公式给出相同值 25）。

## 参考

| 文档 | 说明 |
|------|------|
| `references/priority-formula.md` | 数据优先级公式 `tier * 5 + rank` |
| `references/batch-data-format.md` | 批量 bot 数据目录结构（Flat vs Nested） |

