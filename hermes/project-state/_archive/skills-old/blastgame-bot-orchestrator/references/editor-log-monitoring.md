# Editor.log 批跑监控速查

## 日志位置
```bash
~/AppData/Local/Unity/Editor/Editor.log
```

## 关键模式

### 批次启动
```
[Bot Batch] Levels 60,64,66,67,70: 5 levels × 400 runs × 1 strategy = 2000 games per tier
[Bot Batch] Level L60 (0/5): 400 runs × 1 strategy = 400 games
```
- `0/5` = 第 1 个/共 5 个

### 正常进度（逐关推进）
```
[Bot Batch] Level L64 (1/5): 400 runs × 1 strategy = 400 games
[Bot Batch] Level L70 (4/5): 400 runs × 1 strategy = 400 games
[Bot Batch] Level L99 (19/20): 400 runs × 1 strategy = 400 games
```

### 完成
```
[Bot Batch Jenkins] 完成，最后导出目录: C:\...\batch-range
```
**如果有完整路径** → 正常完成。**如果 `<none>`** → 失败了。

### 失败
```
[Bot Batch Jenkins] 完成，最后导出目录: <none>
```
伴随异常堆栈（通常在日志中更靠前的位置），常见原因：
- Windows MAX_PATH（目录/文件名过长）
- Asset 格式错误（YAML 缩进不对）
- Unity 编译错误

### 错误：路径过长
```
DirectoryNotFoundException: Could not find a part of the path "...\campaign-summary-...csv"
```
→ 缩小 `levelSpec`，每次 ≤ 5 关

### 错误：Asset 格式
格式错误时日志中不一定直接报错，而是批次瞬间完成（0.003秒）且 all 100% WR。
→ 检查 asset 的 DynamicDifficultyConfigs 缩进（必须 4/6 空格）

## 监控 Shell One-liner
```bash
grep "Bot Batch" ~/AppData/Local/Unity/Editor/Editor.log | tail -3
```
