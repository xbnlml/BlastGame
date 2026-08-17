# Unity Package Resolution Failure — Diagnostic Procedure

基于 2026-07-29 实战排查的完整方法论。

## 症状

Unity batch mode 启动时报错：
```
An error occurred while resolving packages
```
或 UPM log 中出现 version fallback 警告。

## 诊断清单（按顺序检查）

### 1. 项目锁定的 Unity 版本

```bash
cat ProjectSettings/ProjectVersion.txt
# 输出：m_EditorVersion: 6000.0.60f1
```

同时在 git 中确认版本何时改变：
```bash
git log --oneline --all -- ProjectSettings/ProjectVersion.txt
```

### 2. 脚本实际使用的 Unity 版本

检查 batch 启动脚本中 `UNITY_EXE` 变量：
```python
UNITY_EXE = os.path.expandvars(
    r'%ProgramFiles%\Unity\Hub\Editor\2022.3.62f2\Editor\Unity.exe')  # ← 是否与 ProjectVersion.txt 一致？
```

### 3. 两个版本的内置包对比

Unity 2022.3 内置：
```bash
cat "C:/Program Files/Unity/Hub/Editor/2022.3.62f2/Editor/Data/Resources/PackageManager/BuiltInPackages/com.unity.ugui/package.json"
# version: 1.0.0
```

Unity 6000 内置：
```bash
cat "C:/Program Files/Unity/Hub/Editor/6000.0.60f1/Editor/Data/Resources/PackageManager/BuiltInPackages/com.unity.ugui/package.json"
# version: 2.0.0
```

### 4. UPM 日志

```bash
cat "$APPDATA/../Local/Unity/Editor/upm.log"
```

关键信息：
- L1: `Command-line: ...2022.3.62f2...` — 确认实际启动的 UnityPackageManager 版本
- L42: `No version 2.0.0 found for package com.unity.ugui on registry, falling back to built-in package version 1.0.0` — fallback 警告
- L48: `project:resolve-packages --> 200` — HTTP 状态码（200=成功但有 fallback）

### 5. 项目包解析 JSON

```bash
cat Library/PackageManager/projectResolution.json | grep unityVersion
# 输出："unityVersion": "6000.0.60f1" — 上一次成功解析使用的 Unity 版本
```

对比其中 `com.unity.ugui` 的 resolvedPath 与实际 PackageCache 目录是否存在。

### 6. PackageCache 版本一致性

```bash
# 检查包的实际版本
cat Library/PackageCache/com.unity.ugui@*/package.json | grep version
# 与 packages-lock.json 中的版本对比
python3 -c "import json; d=json.load(open('Packages/packages-lock.json')); print(d['dependencies']['com.unity.ugui']['version'])"
```

## 2026-07-29 案例证据链

| 文件 | 内容 | 结论 |
|------|------|------|
| `ProjectSettings/ProjectVersion.txt` (git) | `6000.0.60f1` | 项目锁定在 6000 |
| `submit_batch_unity.py` L19 | `2022.3.62f2` | 脚本用错了版本 |
| 2022.3 builtin uGUI | `1.0.0` | 2022.3 没有 uGUI 2.0.0 |
| 6000 builtin uGUI | `2.0.0` | 6000 有 uGUI 2.0.0 |
| `upm.log` L1 | `...2022.3.62f2...` | 确认用了 2022.3 |
| `upm.log` L42 | `falling back to ... 1.0.0` | Fallback 警告 |
| PackageCache | `com.unity.ugui@1.0.0` 存在 | Cache 是 1.0.0 |
| `packages-lock.json` | `com.unity.ugui: 2.0.0` | Lock 文件是 2.0.0 |
| `projectResolution.json` | `unityVersion: 6000.0.60f1` | 上次解析是 6000 |
| `Editor.log` L3 | `6000.0.60f1` | GUI 模式用 6000 正常 |
| `Editor-prev.log` L2 | `6000.0.60f1` | 之前 GUI 也用 6000 |

## 修复

方案 A（推荐）：batch 脚本指向正确的 Unity 版本
```python
UNITY_EXE = os.path.expandvars(
    r'%ProgramFiles%\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe')
# 然后：rm -rf Library && 重新打开项目
```

方案 B（不推荐）：降级项目到 2022.3
```json
// manifest.json
"com.unity.ugui": "1.0.0"  // 改为 2022.3 内置版本
// 删除 packages-lock.json 让 UPM 重新生成
// 风险：BettaFramework/Interface 可能依赖 uGUI 2.0.0 API
```

## 教训

1. **"package 解析失败"的根因往往不是 package 本身**，而是 Unity 版本与项目配置不匹配
2. ProjectVersion.txt 是项目的 Unity 版本唯一真源——先看它
3. PackageCache 删除只是触发器，暴露了早已存在的版本错配
4. 两个版本的 builtin 包版本不同，跨版本运行必然出问题
