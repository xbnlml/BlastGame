# 2026-08-03 修复批次 2：P0 + P1 修复

## P0 修复（5 个）

### P0-1: Planner 探针重复计算
- **问题**: agent_analyze 已调 design_probes.design()，planner 又调一次，浪费 2x 计算
- **修复**: planner.py 先检查 `result['probes']` 是否已存在且 ≥5 条，是则直接复用
- **文件**: tools/planner.py

### P0-2: _design_from_knowledge diff 传参 bug
- **问题**: `et.get_target(targets[0] if isinstance(targets[0], int) else 0)` 传参错误
- **修复**: 加 `lv` 参数，从关卡号查难度；fallback 从 targets 范围推算
- **文件**: tools/design_probes.py

### P0-3: pool.py gap 预剪枝阈值 5 与 <30% 段接近带 4 脱节
- **问题**: gap=4.5 合法组合在枚举阶段被剪掉
- **修复**: 5-tier 枚举 g12/g23/g34/g45 阈值 5→4；3-tier Normal 枚举 g13/g35 保持 5
- **文件**: tools/data/pool.py

### P0-4: _gap_score 硬编码分档 vs rules.json 漂移
- **问题**: 分档值写死在 pool.py 中，改 rules.json 不同步
- **修复**: _gap_score 从 `project-state/rules.json` 动态读 `judge_rules[difficulty]`
- **文件**: tools/data/pool.py

### P0-5: Curator 正则全错
- **问题**: detect_patterns 逐行扫描找不到下行的 gap 信息；PASSED 全大写不匹配日志
- **修复**: 多行匹配（查下一行 gap=）；PASSED→Passed；Warden 通过中文匹配
- **文件**: tools/curator.py

## P1 修复（部分）

### P1-1: W01 单调性检查
- **问题**: sd=[10,50,10,50,10] 极差=40 通过但档位倒挂
- **修复**: check_sd_span 增加单调性检查，T1~T5 必须非递减
- **文件**: tools/warden.py

### P1-2: W03 门槛 2→3 种 ratios
- **文件**: tools/warden.py

### P1-3: W07/W08 warn 不阻塞批次
- **问题**: warn 级检查也阻塞整批
- **修复**: run_warden 增加 warnings 列表，warn 级只追加 warnings 不阻塞
- **文件**: tools/warden.py

## 验证

每批修复后运行 `hermes-verify-batch3.py`（7/7 通过），覆盖 5 个文件编译 + 全部修复点检查。