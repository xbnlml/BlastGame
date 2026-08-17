# 2026-08-04 修复批次 3：auto_loop 稳定化

修复了 auto_loop 连续失败的问题，使 4 关（L159/L174/L186/L197）能正常跑通 planner → apply_probes → submit_batch。

## 修复清单

### sys.path 缺失（全自动模式下最频繁的失败原因）

| 文件 | 问题 | 修复 |
|------|------|------|
| `auto_loop.py` | `from tools.data.pool` 在 `sys.path.insert` 之前执行 | import 前加 `sys.path.insert(0, HERMES)` |
| `planner.py` | 被 subprocess 调用时 `from tools.judge_level` 失败 | `analyze_level` 内加 `sys.path.insert(0, _hermes)` |
| `warden.py` | W06 `from tools.asset_patcher import level_sig` 失败 | 函数内加 `sys.path.insert(0, HERMES)` |

### Warden 自举问题

| 问题 | 修复 |
|------|------|
| W04 `check_unity_lock`: `text=True` 时 GBK 编码报 `UnicodeDecodeError` | `text=False` + `decode('gbk', errors='replace')` |
| W05 `check_no_git`: 扫描到 `warden.py` 自身含 git 字符串 | 跳过 `fn == 'warden.py'` |
| W06 `check_no_git`: 返回 NoneType 报 `argument of type 'NoneType' is not iterable` | 加 try/except 容错 |

### _make_config 单调性

`_make_config` 从 phase2 候选或知识库生成的探针 sd 顺序可能乱序（如 [40,25,14,30,20]），W01 单调性检查拦截。修复：末尾加 `result.sort(key=lambda r: r['sd'])` 确保 T1~T5 单调递增。

### 其他

- `apply_probes.py` `parse_levels`: 空字符串崩溃（`ValueError: invalid literal for int() with base 10: ''`）。修复：`if not part: continue`
- `auto_loop.py` `phase_analyze`: 兼容新旧 planner 输出格式（`{results: [{level, ...}]}` vs `{lv: {...}}`）。修复：`isinstance(data, dict)` 分叉处理
- `pool.py` `filter_verified`: 从 git HEAD 恢复后丢失。修复：重新添加
- `pool.py` `dedup_records`: `seen = {}` 被误删。修复：重新添加
- `planner.py` `agent_analyze` JSON 解析: `data.items()` 取到 `action` 当 combo。修复：`data.get('results', [])` 取 `results[0]`

## 验证

每次修复后 `python3 -c "compile(code)"` 验证编译，再 `background` 重启 auto_loop。共重启 5 次才全部跑通。最终 `_make_config` 单调性修复后 auto_loop 能正常走到 Unity batch 阶段。