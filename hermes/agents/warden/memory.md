# Warden Memory
# 记录安全规则与经过当前监督协议验证的事件。

## 已知禁止模式
- git checkout, git reset, git restore, git clean
- rm -rf（任意路径）
- 删除 Library/、PackageCache/
- 修改 .meta、packages-lock.json

## 系统铁则

### 路径格式
- `search_files` 使用 Windows 原生路径；传 `D:/path`，不要传 MSYS2 `/d/`。

### 文件安全
- 不允许修改 `$BLASTGAME_REPO` 下任何文件，除非用户明确授权。
- Python 工具只通过 `write_ddc` 修改 test/ 下的 asset。
- 禁止写 funnel_b/、Library/、Temp/。
- 禁止删除源数据文件（Library/PackageCache/.meta/stage-data/assist/ref）。

### Unity
- Unity batch mode 异常时先核对 Unity 进程和实际 CSV 产物。
- `AssetDatabase.Refresh()` 必须使用 `ImportAssetOptions.ForceUpdate`，避免 batch 读取旧缓存。
- 禁止操作 .meta、Library/、Packages/packages-lock.json、manifest.json。

### 配置同步
- 探针通过 `apply_probes.py` 写入 asset；提交批跑前必须核对 probe、asset 与 Warden 结果。

## 最近安全事件

### 2026-07-31 — tools/ 目录扫描
- 扫描 `tools/` 中的危险 git 命令；唯一命中是 Warden 自身禁止词列表。
- 结论：未发现实际安全违规。

### 2026-08-25 — 监督解析器修复
- 旧 Curator 将多轮合法 Phase 序列扁平化，曾批量生成虚假的“阶段顺序异常”。
- 旧三态检查遗漏“接近”，也会生成虚假的“未发现判定结果”。
- 这些不可核验的自动事件已从 memory 移除；原始 auto-log 保留历史证据。
- 从本日期起，只记录经逐轮 phase 状态机和结构化 FINAL SUMMARY 解析后的事件。
