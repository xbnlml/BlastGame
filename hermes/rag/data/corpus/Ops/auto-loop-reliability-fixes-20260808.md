# auto_loop 全自动流程可靠性修复（2026-08-08）

> 场景：85/119/120 全自动调优 6 轮。用户要求"6 轮要跑满，出问题你们自己解决"。跑完发现 L85 只显示 r5/6 留在 pending（实际已跑 6 轮）→ 排查出 2 个 bug。
> 关联：`scripts/auto_loop.py`（编排器）、`tools/judge_level.py`（轮数判定）、`tools/planner.py`（探针设计）。

## 一、judge_level.py 轮数返回值 bug（MAX ROUNDS 检查失效）

- **现象**：L85 跑满 6 轮仍显示 r5/6、留 pending（auto_loop 退出码 1）；L119 正常触发 MAX ROUNDS。
- **根因**（judge_level.py `judge_with_rounds` 不合格分支）：
  ```python
  if rnd >= MAX_ROUNDS - 1:
      inc_round(lv)          # ← 递增了但没把返回值赋给 rnd！
      action = '改关卡'
  else:
      rnd = inc_round(lv)    # ← 这里赋值了
  ```
  `inc_round(lv)` 返回值没赋给 `rnd` → 返回旧轮数（5）→ auto_loop 的 `status['round'] >= MAX_ROUNDS` 检查判 5<6 不触发 → 该关永远留 pending。
- **修复**：改关卡分支也 `rnd = inc_round(lv)`。
- **铁则**：**函数返回新状态（轮数/计数/新值）时必须接住返回值，不能只调用忽略**。本类 bug 已第三次出现（memory 总结"每次优化集中在 3 类问题——硬编码路径、忽略返回值、缺失前置校验"）。
- **轮数语义**：`_rounds.json` 初始值可能非 0（如 119 初始=1 是历史遗留），6 轮后变 7 属正常（"已跑 7 次"）；判定"跑满"看 judge 返回的 round 与 action='改关卡'，不看 _rounds 绝对值。

## 二、auto_loop extract_json 只支持单行 JSON（planner 多行输出解析失败）

- **现象**：auto_loop 启动即失败 `probe_design_failed_r1`，日志 `planner: could not parse JSON output`。
- **根因**：`planner.py --output json` 用 `json.dumps(results, indent=2)` 输出**多行格式化 JSON**，且 `analyze_level()` 内部 debug print（"① 当前最优…"）混入 stdout；auto_loop 的 `extract_json` 只逐行找 `{` 开头的完整单行 JSON → 全失败。
- **修复**：extract_json 增加 **brace-span 提取**策略（第 2 优先级）：`stdout[stdout.find('{'): stdout.rfind('}')+1]` 再 `json.loads`，兼容"debug 文本 + 多行 JSON"混合输出。
- **验证**：用真实 planner 输出测 extract_json（含 debug 噪声），单行 JSON 回归、无 JSON 返回 None。

## 三、探针可达性检查缺陷（85/119 打 6 轮无效探针）

- **现象**：L85（目标 90/90/75/60/60）6 轮探针结果恒 72.5/72.5/61.8/44.8/44.8 无变化；L119 同样。判定都失败（T1 离目标 17-23pp）。
- **根因**：design_probes/planner 反推目标段时**没检查关卡可达性**——verified 最高 wr（L85=72.5、L119=61.8）远低于 T1/T2 目标段 → 探针目标段物理不可达 → 每轮打的探针都落在已验证区域附近，数据无新信息 → 6 轮空转。
- **教训**：探针设计前先看该关 verified（bot/summary/phase0）最高 wr vs 目标。若最高档目标段差 >15pp 且 phase1/2 也覆盖不到 → **直接判定改关卡，不要浪费 6 轮探针**。改关卡批次第一次跑失败（T1 段门内 0 候选）是常见现象：改关卡后数据重新积累、首次覆盖不足，需看 phase1_raw 实际采到的段判断"改的方向对不对"，而不是只看 summary failed。
- 用户质疑"其他两关没改观？你怎么设计的探针"——回答要点：探针按目标段反推 needs 设计，但**没查关卡上限导致无效探针**，这是设计器缺陷不是探针执行问题。
- **改关卡正例实证（2026-08-09）**：57/64/93/110/119/138 改关卡后批次（08-09T02:54）→ **93/110/119 成功**（93: T4/T5 43.1→59.5、T1 66→90.7 全达标入库；119: T1 61.8→81.2 全绿入库；110: T3-T5 绿、T1/T2 76.9 黄区用户裁定入库）；**57/64/138 仍 failed**（64 T1 门内 0、138 T3 门内 0、57 最终选档失败）。判定改关卡方向对不对：**看第二次批次 phase1_raw 采到哪些段**——采到目标段=方向对（93/110/119），仍采不到=再改（57/64/138 需继续）。
- **改关卡正例实证 2（2026-08-10）**：64/85/138 二次改关卡后批次（08-10T00:16）→ **3 关全 ok 全达标入库**：85 从 72.5 天花板→87.9/87.9/73.9/61.1/61.1（全档差≤2.1pp）、138 从 70.9→83.0/83.0/65.0/49.2/49.2（差≤2pp）、64 从\"无单调组合\"→72.4/67.4/56.9/41.8/27.2（仅 T1 差 7.6pp 黄）。**结论：一次改关卡方向不对≠该改，第二次改（加大易化）后成功；85/138 两次改才到位，64 一次改就出组合**。改关卡是有效手段，方向靠\"批次 phase1_raw 覆盖段\"反馈迭代，不是一次定生死。

## 四、全自动流程健康保障

- auto_loop 主循环：MAX_ROUNDS=6，5 phase（agent_analyze→apply_probes→submit_batch→dump_pools→judge），合格只标记"待确认入库"、满 6 轮只标记"待确认改关卡"，**都不自动落盘**（用户铁则）。
- watchdog 模式：`scripts/auto_loop_watchdog.py`（可复制到 ~/AppData/Local/hermes/scripts/ 供 cron 用）——检查日志 mtime 推进（>30min 未更新报警）、Unity 进程、FINAL SUMMARY 结果、_rounds.json 轮数。tasklist 输出是 GBK，必须 bytes 模式 + `decode('gbk', errors='ignore')`。
- C# 改动（phase1 重设计等）是否编译通过：看 Unity batch 进程是否存活超过启动后 1-2 分钟（编译失败会立即退出），或看 telemetry 是否开始生成。

## 五、已满轮关重启 auto_loop 的行为（2026-08-09 实证）

- **现象**：L85 上次 auto_loop 已满 6 轮（_rounds=6）未处理，这次 57/85/138 批次重启 auto_loop → L85 显示 r7/6、第一轮 judge 直接判改关卡（不合格→rnd=6≥5→inc 到 7→action=改关卡），**不再跑批**；整批 5 轮就结束（pending 清空提前退出）。
- **机制**：`_rounds.json` 是跨批次累计的。已满 6 轮的关重新进 auto_loop，round 1 的 judge 就触发 MAX ROUNDS 分支 → 立即标记改关卡。
- **使用含义**：想重跑已满轮关（如改关卡后）必须先 `judge_level.py --rounds-reset <lv>` 清轮数，否则 auto_loop 不会给它跑批。判断"该关是否真跑了批"看日志 Phase 3 的 submit 关卡列表，不是看 FINAL SUMMARY 的 r 数字。
- 改关卡后首轮/次轮即合格的正面证据：L83 r2 合格（78.5/58.5/44.2/33.3/25.2）、L57 r1 合格（93.3/93.3/64.0/49.0/49.0）——探针有效时不需要 6 轮。
