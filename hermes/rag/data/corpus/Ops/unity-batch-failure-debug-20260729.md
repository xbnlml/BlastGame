# Unity Batch Mode 突然失败诊断案例（2026-07-29）

## 症状
`submit_batch_unity.py` 提交后 Unity 报 "An error occurred while resolving packages"，exit code 1。

## 时间线
1. 上午运行多批 bot 正常
2. 重写了 `submit_batch_unity.py`（解耦 probe_configs）
3. 删除了 L172 的 .meta 文件（已通过 git 恢复）
4. 删除了 Library/PackageCache 目录
5. 之后所有 batch mode 提交都失败

## 错误排查路径（按时间顺序）

### 误判 #1：AssetDatabase 缓存
猜测：write_ddc 后 Unity 读旧缓存。尝试 C# 加 ForceUpdate（无效，且根因不在此）。

### 误判 #2：probe_configs.json 覆盖 asset
发现 submit 脚本从 probe_configs.json 读配置写 asset，与我们手动 write_ddc 打架。
部分正确——确实有冲突，但不是 package 解析错误的根因。

### 误判 #3：PackageCache / ugui 版本冲突
Unity 2022.3 内置 ugui 1.0.0，manifest 要 2.0.0。删 PackageCache 后缺 2.0.0。
部分正确——如果用了 Unity 2022，确实会因版本冲突失败。

### 误判 #4：Unity 进程未关
`tasklist` 发现 Unity.exe 还在运行，batch mode 报 "another instance"。
部分正确——有些失败确实是因为 Unity 没关。

### 真正根因（由子 agent 发现）
`ProjectSettings/ProjectVersion.txt` 显示 `m_EditorVersion: 6000.0.60f1`。
但重写后的 `submit_batch_unity.py` 第 19 行硬编码了：
```python
UNITY_EXE = r'%ProgramFiles%\Unity\Hub\Editor\2022.3.62f2\Editor\Unity.exe'
```
应该是：
```python
UNITY_EXE = r'%ProgramFiles%\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe'
```
Unity 2022.3 内置 ugui 1.0.0，6000 内置 2.0.0。用 2022 打开 6000 项目必然报包解析错误。

## 教训
1. **先查自己的改动**——不是猜外部原因
2. **Hardcoded 路径是隐藏炸弹**——应该从 `ProjectVersion.txt` 自动读取
3. **错误信息会误导**——"resolving packages" 掩盖了版本错配
4. **删 PackageCache 是火上浇油**——把原本正常的环境搞坏了
5. **子 agent 独立视角有价值**——不被之前的错误思路带偏
