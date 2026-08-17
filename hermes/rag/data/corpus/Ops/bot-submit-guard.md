---
name: blastgame-bot-submit-guard
description: "Use before bot runs. Verify asset, then check results after."
---

# Bot 提交前置检查与常见坑

## 提交前检查清单

1. **Unity 已关闭** — `tasklist | grep Unity.exe` 确认无残留进程。batch mode 不能和编辑器同时开。若 Unity 还开着，`taskkill /F /IM Unity.exe` 强制关闭
2. **Asset 配置验证** — `read_ddc(lv)` 确认每档 sd/sc/ratios/of 与预期一致
3. **写后读回** — `write_ddc` 后立即 `read_ddc` 比对
4. **策略确认** — `--strategy scoring_opt_vg` 为默认值
5. **档位 dedup** — Normal 模式 Unity 自动跳过重复配置

## 跑完后检查

1. **Asset 是否被反写** — 检查 repo asset 是否被 Unity 缓存覆盖（解耦 probe_configs 后此问题已修复）
2. **Bot 实际跑配置** — 对照 campaign-summary CSV sd/sc/ratios/of 与 asset 一致
3. **level_sig 关卡设计校验** — 池子导入时自动比对 bot 快照与当前 asset（去掉 DDC 块后的 SHA256 签名），关卡设计变更的旧数据自动跳过
4. **Pool refresh** — 确认新数据已导入

## 用户沟通铁则

1. **先展示方案再执行** — 不要直接动手，等确认
2. **全自动 = 不问你** — 用户说"全自动"后，自己做决定、出错自己修、上网查方案，别再问用户
3. **被纠正立刻承认** — 不找借口，不争辩
4. **报错不盲目重试** — 失败超过2次停下来诊断根因——`tasklist | grep Unity.exe` 永远是第一步
5. **不准让用户干活** — `taskkill /F /IM Unity.exe` 自己来，开/关 Unity 说明为什么需要

## 常见坑

### Unity 版本写错导致包解析失败（🔴 新坑！）
**现象：** batch mode 反复报 `error while resolving packages`，即使 Unity 已关闭、所有代码还原到 git。
**根因：** `submit_batch_unity.py` 的 `UNITY_EXE` 硬编码了错误的 Unity 版本。项目用 6000.0.60f1 但我改脚本时写成了 2022.3.62f2。2022 的 builtin ugui 只有 1.0.0，manifest 要 2.0.0，导致包解析失败。
**诊断：** 检查 `ProjectSettings/ProjectVersion.txt` 确认项目版本，对比 submit 脚本里的 `UNITY_EXE` 路径。
**注意：** `check_unity.py` 可验证路径是否存在。

### Unity 未关闭导致 batch 失败（🔴 高频错误！先查这个再查别的）

**现象：** 提交 bot 后秒报 `error while resolving packages` 或 `Fatal Error`。
**根因：** Unity 编辑器还开着，batch mode 无法同时打开同一项目。
**注意：** 错误消息可能是 "resolving packages" 而不是 "another instance"，极具误导性。
**铁律：任何 batch mode 失败，第一步永远是 `tasklist | grep Unity.exe`。** 不要怀疑包版本、不要怀疑缓存、不要删文件、不要改 lock——先确认 Unity 进程不存在。

### Unity AssetDatabase 缓存覆盖
**现象：** write_ddc 后 Unity 批跑读到旧配置。
**根因：** `AssetDatabase.Refresh()` 不加 `ImportAssetOptions.ForceUpdate` 不一定触发重导。
**注意：** 优先检查 probe_configs 是否过期，这是更常见的根因。

### Tier 标签不可信
池子 `source_tier` 只是来源标注。选组合禁止按 tier 分组。参 `blastgame-pool-data-integrity`.

### 跑完直接给结论
先展示完整数据表格再让用户判定，不自己判入库。

## 破坏性操作（永禁！）

- **绝对禁止任何 git 命令** — git checkout / reset / clean / restore / commit / push / pull / stash / add / merge / rebase / revert 全部禁止。用户通过 SourceTree 自行管理。只读命令(git status/log/diff)也不行
- **不要删 `Library/` 目录** — Unity 项目核心缓存，删除需用户确认
- **不要删 `PackageCache`** — 删后 batch mode 无法解析包，必须 GUI 重新下载
- **不要删 `.meta` 文件** — 删后包解析链断裂，必须 git checkout 恢复
- **不要改 `packages-lock.json`** — 用户已明确禁止
- **`submit_batch_unity.py` 现在只有提交功能** — `probe_configs.json` 不再被隐式读取。改 asset 用 `write_ddc` 或 `apply_probes.py`，两个操作独立
- **任何删除/修改 Unity 项目的操作，先问用户**