# Batch 完成后的例行操作

每次 Unity Bot 批跑完成后，按此清单执行。

## 0. 检测批次完成（不轮询）

监控 `BuildLogs/auto-batch-last-export.txt` 的 mtime：

```python
old_mtime = os.stat("BuildLogs/auto-batch-last-export.txt").st_mtime
while os.stat("BuildLogs/auto-batch-last-export.txt").st_mtime == old_mtime:
    time.sleep(1)
# mtime 变了 → 批次完成
```

脚本 `~/.hermes/scripts/monitor_bot.py` 在后台运行，检测到变化后自动关弹窗、读结果、打标记。

## 1. 关闭 Explorer 弹窗（如未自动关闭）

已修改 Unity 端：**只在整个批次完成时弹一次文件夹**（`EditorUtility.RevealInFinder` 在 `BlastBotAutoBatchTrigger` 末尾），不再每档弹一次。

如果弹窗还在：
```powershell
# 方法A（推荐）：写 .ps1 文件运行
(New-Object -ComObject Shell.Application).Windows() | Where-Object { $_.LocationURL -like "*telemetry*" } | ForEach-Object { $_.Quit() }

# 方法B（bash终端）：先写文件再执行
powershell -NoProfile -ExecutionPolicy Bypass -File close_telemetry.ps1
```

> ⚠️ 不要在 bash 终端直接内联这个命令——`$_` 会被 bash 解释导致报错。用 .ps1 文件绕过。

## 2. 读取结果

```python
import csv, glob
bot_dir = sorted(glob.glob('telemetry/bot/*'))[-1]  # 最新批次
for d in sorted(glob.glob(f'{bot_dir}/L*-range/')):
    with open(glob.glob(f'{d}/campaign-summary-*.csv')[0], encoding='utf-8-sig') as f:
        r = next(csv.DictReader(f))
        wr = float(r['winkate']) * 100
    with open(glob.glob(f'{d}/campaign-attempts-*.csv')[0], encoding='utf-8-sig') as f:
        r2 = next(csv.DictReader(f))
        print(f'WR={wr:.1f}%  sd={r2["startDifficulty"]} r={r2["shuffleSplitRatios"]}')
```

## 3. 规则判定

过检查表三张（来自 `blastgame-multi-tier-designer`）：
① 数据源判定 ② 合格判定 ③ 结果判定

## 4. 报告——表格展示

```
T1: xx%  sd=xx r=...
T3: xx%  sd=xx r=...
T5: xx%  sd=xx r=...
```

## 5. 合格则入库

## 6. 提交下一关 / 重试
