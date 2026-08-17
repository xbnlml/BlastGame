# Batch Mode 实战教训（2026-07-16）

## Unity Batch Mode 提交

**入口：** `BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine`
**工具：** `scripts/submit_batch_unity.py`

命令行格式：
```bash
Unity.exe -batchMode -nographics -projectPath "..." \
  -executeMethod BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine \
  -BlastBotBatchLevels "56,57,71,86" \
  -BlastBotBatchRunCount 400 \
  -BlastBotBatchTiers "1,2,3,4,5" \
  -logFile - -quit
```

### Batch mode 的核心优势
- 每次全新进程，无 EditorApplication.update 堆栈污染
- `_isRunning` 锁死在进程结束后自动归零
- 自动 import 外部修改的 .asset（启动时 AssetDatabase.Refresh）
- `-logFile -` 实时输出到 stdout，可 grep 监控进度
- `window.Close()` NRE 不致命——数据已写入，exit code 1 不影响数据完整性

### window.Close() NRE 问题
在 batch mode 下，`ScriptableObject.CreateInstance<BlastWorkbenchWindow>()` 创建的窗口无法正常关闭。`window.Close()` 抛出 NullReferenceException 但已在 try-catch 中捕获，数据在异常发生前已完成导出。这是已知问题，不致命。

### 数据完整性检查
Batch mode 退出后，检查 `telemetry/bot/` 最新目录。如果 T1-T5 5 个子目录齐全且各有 `campaign-summary-*.csv`，则数据完整。

## Editor Trigger 监控失败的原因链

1. 每次批次完成后 `_isRunning` 保持 `true`（NRE 发生在 `_isRunning = false` 之前）
2. 下次 EditorApplication.update 触发时 `if (_isRunning) return;` 跳过
3. `pre_dirs` 在消费后捕获 → Unity 已创建 batch 目录 → `current_dirs - pre_dirs` 永远为空
4. 除非重启 Unity，Trigger 永久不可用

## 参数调优实战教训

### Ratios 不是数值大小而是分布节奏
- `10,10,10,1,1` 和 `1,1,1,1,1` 本质是同一类分布（前重后轻）
- `5,3,2,1,1` 也可以用 `8,2,1,1,1` 或 `3,3,1,2,3`
- Ratios 值不需要 10，`3,3,1,2,3` 效果一样

### of 不对称性
- L79：of↑0.5→0.8 让 WR 从 85% 降到 50%（大杠杆，正常方向）
- L59：of↓0.5→0.03 让 WR 从 77% 降到 50%（倒挂——高 of = 高 WR）
- L81：of 0.11~0.5 全部产出相同 WR（死区）。只有 of=0.107 跳出来
- L86：of 0.15~0.8 完全无效
- **结论：先用双向极端值探方向，再沿确认方向梯度探测。无效就换。**

### 参数死区
部分关卡在某参数范围内完全无响应。识别：一轮探针后多个不同参数产出相同 WR → 缩短步长或跳极端值尝试突破。

### Phase2 WR 不可信
- L56 T3：phase2 预估 72.5% → bot 实测 80.5%（差 +8pp）
- L86 T1：phase2 预估 93.5% → bot 实测 83.0%（差 -10.5pp）
`write_ddc` v5.3+ 已自动修正此问题。

### m_Name 错误：关卡名不对导致跑错关

用其他关的 asset 做模板重建时，`m_Name: 51` 未改为目标关号。Unity 用 `m_Name` 识别关卡身份，bot 因此一直玩 51 关。

**排查：`grep "m_Name:" *.asset`，应等于关卡号。**
**修复：`sed -i 's/m_Name: 51/m_Name: 59/'`**

### 关卡参数丢失：模板替换覆盖 myStage/myStack

不能用模板整体替换。每关的 `m_Name`、`myStage`（牌面）、`myStack`（棋盘尺寸/池值）等参数不同。必须从备份恢复，只替换 tiers 段。

### Batch mode 空 CSV 调试流程

1. `grep "customCellDrawingListV2:" *.asset | head -1` → 缩进 = 0？
2. `grep "m_Name:" *.asset` → 等于关卡号？
3. `grep "difficultyLevel:" *.asset` → 匹配 target？
4. `python -c "from tools.asset_patcher import read_ddc; print(len(read_ddc(LV)))"` → =5？
5. 看 CSV 数据：winCount=400×关数、level=51 → 多关合并(新 bot 分支)
6. 看 CSV 数据：winkate=1.0、clearedCellCount=0 → 缩进错误

## 改关卡数据过滤 (2026-07-16)

关卡修改后旧数据失效。更新时间防线步骤：
1. 编辑 `stage-data/_last_refresh.json` → `asset_updated_at.lv` 设为修改日期
2. 重跑 `dump_level_pools.py` → 自动过滤修改前的 bot/opt 数据
3. 改关卡标记后清空 stage-data pool、probe_configs。**asset 不动**（空配置 Unity 报错）

## L70 T4 sd 突破 (2026-07-16)

L70 T5 长期被压在 4.2%，多次尝试调 ratios 无效。最终发现 **sd 才是 T4/T5 的精确杠杆**：
- sd=20 + ratios=1,1,1,4,1 → T4=4.0%, T5=4.2%
- **sd=15 + ratios=1,1,1,6,1 → T5=14.5%**（超硬底线 5%，可入库）
- sd=17 → T4=0.5%（突变下降）

**教训：ratios 调不动时换 sd。每关参数杠杆不同。**

## 16 组预设 ratios (2026-07-16)

`BlastMultiTierPhase1AdaptiveSampler.cs` 预定义了系统化 ratios：
```
10,1,1,1,1  1,10,1,1,1  1,1,10,1,1  1,1,1,10,1  1,1,1,1,10
10,10,1,1,1  1,1,1,10,10  10,10,10,1,1  1,1,10,10,10
1,10,10,10,1  10,1,1,1,10  10,10,1,10,10  1,10,1,10,1
10,1,10,1,10  5,5,1,5,5  1,1,1,1,1
```
固定 of=0.5/sc=5，配合 sd=20 起步，系统化覆盖 ratios 空间。

## 批跑代码路径 (2026-07-18 排查记录)

batch mode 的执行链路与 editor trigger 不同：

**入口 → 调用链：**
```
BlastBotJenkinsBatchEntry.RunFromCommandLine
  → window.RunBotBatchByLevelRangeForJenkins()     [BlastWorkbenchWindow.Bot.cs]
    → for tier in forcedTiers:                       [外层 tier 循环]
      → RunBotBatchByLevelRange()                    [内层 level 循环]
        → create BlastBotBatchRunRequest {forcedTier}
        → BlastBotBatchRunner.Run(request)           [实际 bot 执行]
          → BuildAttemptResult(..., request)          [构建 attempt 记录]
```

**关键区分：`BlastBotCampaignRunner` 是 editor trigger/Workbench 手动运行用的；batch mode 走的是 `BlastBotBatchRunner`。**

### 编译回退陷阱
当 C# 文件修改后重新编译失败时，Unity batch mode **静默回退到上次成功编译的旧 DLL**。这意味着：
- 所有本次添加的 Debug.Log 全部不生效
- 即使某个文件的改动是正确的，只要同一 assembly 下任何文件有编译错误，整个 assembly 回退
- 唯一的检测手段：启动日志中查找 `LogAssemblyErrors` 或具体错误
- 回退后旧 DLL 仍能正确完成批跑，输出数据，但 debug log 丢失

### 排查建议
- `-BlastBotBatchDedupeEnabled false` — 如需排除 dedup 干扰，在 cmd 参数中加入
- 单档提交：`--tiers 1` 只跑一档，减少多档交互
- asset 备份：`write_ddc` 自动生成 `.asset.bak`，可用 `read_ddc` 查验文件是否正确
