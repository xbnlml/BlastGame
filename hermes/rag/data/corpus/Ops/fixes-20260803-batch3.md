# 2026-08-03 修复批次 3 — auto_loop + warden 启动修复

## 背景
auto_loop 启动失败链：planner 输出格式变更 → auto_loop 解析不到 probes → 空 levels 传给 apply_probes → parse_levels 崩溃；Warden 自身有 3 个 bug 拦截批跑。

## P0: auto_loop 启动

### auto_loop.py
- **sys.path 修复**：import 前加 `sys.path.insert(0, HERMES)`，解决 `ModuleNotFoundError: No module named 'tools.data'`
- **phase_analyze 兼容新旧 planner 格式**：planner 输出从 `{results: [{level, ...}]}` 改为 `{lv: {...}}`，`data.get('results', [])` 返回空列表。修复：兼容新旧格式——`isinstance(data, dict)` 时分叉处理 `results` 键或直接遍历 `items()`

### apply_probes.py
- **parse_levels 空字符串崩溃**：`ValueError: invalid literal for int() with base 10: ''` 当 auto_loop 传入空 levels 字符串时。修复：`parse_levels` 中 `if not part: continue` 跳过空段。

### pool.py
- **filter_verified 恢复**：git HEAD 恢复 pool.py 后丢失，重新添加
- **dedup_records `seen = {}` 恢复**：`NameError: name 'seen' is not defined`，重新添加

## P1: Warden 自身 bug

### W04 check_unity_lock
- **问题**：Windows tasklist 输出 GBK 编码，`text=True` 时 utf-8 解码报 `UnicodeDecodeError`
- **修复**：`text=False` 取 bytes → `decode('gbk', errors='replace')`

### W05 check_no_git
- **问题**：warden.py 自身字符串含 `'git checkout'` 等，被扫描到后报自身违规
- **修复**：`fn == 'warden.py': continue` 跳过自身

### W06 check_asset_hash
- **问题**：从 auto_loop 调用时 Python 路径不包含 `hermes/`，报 `No module named 'tools.asset_patcher'`
- **修复**：`sys.path.insert(0, HERMES)` 再 import

## 验证
- 7/7 ad-hoc 验证通过（compile/导入链/filter_verified/sys.path 修复/planner 兼容/parse_levels 空字符串/warden 全功能）