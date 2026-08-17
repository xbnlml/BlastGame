# auto_loop 整轮跳过：超时链 + 探针合规根因（2026-08-04）

## 场景

用户授权全自动调优 6 关（154/162/165/176/182/198），auto_loop 启动后每轮全部 Still pending，FINAL SUMMARY 显示 6 关全部失败，日志模式：

```
[Phase 1/5] planner FAILED after retries
L154: design_probes --write FAILED
L198: design_probes --write FAILED
L162: 0 probes, judge=no_combo, combo quality=?
[Phase 2/5] apply_probes → write asset
apply_probes FAILED → skipping this round
```

## 排查链（复用模式）

1. **auto_loop 日志只记 exit code**——看不到失败原因。先手动跑被卡住的命令：
   ```bash
   python tools/apply_probes.py 176,182,165,162   # 看 Warden 拦截详情
   ```
   输出：`L162: ⛔ Warden BLOCKED — W01 sd跨度≥10pp: sd 范围 0-5=5pp; W03 ratios≥2种: 只有 1 种`

2. **手动跑 planner 复现超时**：
   ```bash
   DESIGN_PROBES_QUIET=1 python tools/planner.py --levels 154,162 --output json
   # → subprocess.TimeoutExpired: agent_analyze.py timed out after 120 seconds
   ```
   agent_analyze 内部调 LLM（DeepSeek），单关实测 ~180s > timeout=120。

3. **手动计时 design() 定位第二个超时**：
   ```bash
   python -c "import time; from tools.design_probes import design; t0=time.time(); design(154); print(f'{time.time()-t0:.1f}s')"
   # → L154 design: 135.7s（param_knowledge 全量统计）
   ```
   auto_loop fallback_design_probes timeout=60 再次超时。

4. **检查 probe_configs.json 残留**：L154/L198 因 design_probes FAILED，用的是上次残留的旧通用模板（sd30/35/40/45/50 + 固定 ratios），不是新设计。

5. **检查 design() 源码找 None 路径**：`if len(bot400) < 3: return None`（L162 只有 1 条 bot400）→ auto_loop fallback 填默认 sd=0 → W01/W03 双拦。

## 修复清单

| 文件 | 修改 |
|------|------|
| `tools/planner.py` L27 | subprocess timeout 120→300（agent_analyze LLM 需 ~180s） |
| `scripts/auto_loop.py` phase_analyze | 调 planner timeout 120→600 |
| `scripts/auto_loop.py` fallback_design_probes | timeout 60→300（param_knowledge 统计 135s） |
| `tools/design_probes.py` design() | bot400<3 时不再 return None：有 phase2 候选走 `_make_config`，无候选走 `_design_gap_focused`（sd 30-50 阶梯 × 5 ratios，天然过 W01/W03） |
| `tools/design_probes.py` `_design_from_knowledge` | 输出前 `result.sort(key=lambda r: r['sd'])`（knowledge 按目标查表返回 sd 乱序 27/32/12/22/22 → W01 单调性拦截） |

## 验证

- L154 knowledge 探针排序后 [12,22,22,27,32]（5 种 ratios、跨度 20pp）✅
- L162 gap-focused 探针 [30,35,40,45,50] ✅
- apply_probes 6 关全部 Warden 通过 + 写入 asset ✅
- 5/5 ad-hoc 验证通过

## 通用教训

1. **全自动流程中"超时即失败"会级联**：planner 超时 → 无探针 → fallback → fallback 超时 → 旧配置残留 → apply_probes 被 Warden 拦 → 整轮跳过。修一个不够，要沿调用链全部排查。
2. **subprocess timeout 必须 > 实测最慢路径**：agent_analyze（LLM 调用）~3min、param_knowledge（全量统计）~2min。宁可 timeout 给 5-10 分钟，不要 60-120s。
3. **fallback 必须生成合规探针**：默认占位（sd=0/ratios 单一）必然过不了 Warden W01/W03。缺口感知设计（`_design_gap_focused`）是安全的兜底。
4. **日志只记 exit code 时，手动跑命令看真实报错**是第一步；用 `timeout N python ...` 包一层测耗时。
