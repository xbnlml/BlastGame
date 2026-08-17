# L172 池子数据污染案例（2026-07-29）

## 背景
L172 已入库，配置为 sd=32/40/34（T1/T3/T5），来源为外部 101-200 bot 400局数据（WR=96.8%/68.8%/48.8%）。

## 发现

### 数据不一致
- 外部 101-200 07-18 批跑：L172 T1 winkate=0.83, sd=36, r=4,1,6, of=0.17
- 外部 101-200 07-20 批跑：L172 T1 winkate=0.97, sd=36, r=4,1,6, of=0.17
- 外部 101-200 07-20 批跑：L172 T3 winkate=0.968, sd=32, r=4,1,5, of=0.13

同一配置（sd=36）两次批跑差 14pp（83% vs 97%）。

### 池子档位标签错位
池子 `get_bot_records('172')` 返回 T1 WR=96.8% 配置为 sd=32/r=4,1,5。但原始 CSV 中 sd=32/r=4,1,5 在 **T3 批跑目录** 下（L101-200-T3-...），不在 T1 目录下。

**根因**：`get_level_pool.py` 的去重逻辑把 T3 批跑的数据标成了 T1。因为配置 `(sd=32,sc=3,ratios=4,1,5,of=0.13)` 的 tier 标签被后批覆盖。

### Asset 被 Unity 反写
Python `write_ddc` 写入 sd=32/40/34 后立即 `read_ddc` 验证通过。但 Unity 批跑完成后，asset 被恢复为旧配置（sd=36/5/34）。

T3 档位甚至被写成了一个来自优化器批跑且从未出现在的资产里的 sd=5。

**根因**：Unity `AssetDatabase.Refresh()` 不加 `ForceUpdate` 时，不强制重导已缓存的 asset。

## 修复

1. **C# 补丁**：`BlastBotJenkinsBatchEntry.cs` 第77行 `AssetDatabase.Refresh()` → `AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate)`
2. **池子 tier 改名**：`tier` → `source_tier`，明确这是来源标注不是档位绑定
3. **验证四参**：不只是 sd，必须同时验证 sd/sc/ratios/of
4. **写入即验证**：`write_ddc` 后立即 `read_ddc`，批跑后再次验证

## 教训
- 池子只做快速索引，最终判断必须查原始 CSV
- Asset 写入后不能假设生效，必须对比 bot 实际跑的配置
- 同一配置不同批跑差 14pp 是正常波动（不同 bot 策略、不同时间）
