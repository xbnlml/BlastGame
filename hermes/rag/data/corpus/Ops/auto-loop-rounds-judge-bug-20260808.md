# judge_level 改关卡分支 rnd 赋值 bug → 跑满 6 轮仍 pending（2026-08-08）

> 场景：auto_loop 85/119/120 跑满 6 轮，FINAL SUMMARY 里 **L85 显示 r5/6 仍 pending**（实际已跑 6 轮 batch），L119 正常 r6/6 判改关卡。用户要求"6 轮必须跑满"——这 bug 会导致跑满轮数却永远不判改关卡。
> 关联：`tools/judge_level.py` `judge_with_rounds()`、`scripts/auto_loop.py` MAX ROUNDS 分支。

## 症状
```
FINAL SUMMARY
  🔄 Still pending: 1 levels
     L85   ← 已跑满 6 轮 batch，但没进 failed（待用户确认改关卡）
_rounds.json: "85": 6   ← 轮数文件已到 6，但 judge 返回的 round 字段是 5
```

## 根因（judge_level.py judge_with_rounds 不合格分支）
```python
elif result == '不合格':
    if rnd >= MAX_ROUNDS - 1:   # rnd=5 时进这里
        inc_round(lv)           # ← BUG：递增了但返回值没赋给 rnd！
        action = '改关卡'
    else:
        rnd = inc_round(lv)     # ← 正确路径：赋值
```
- **改关卡分支 `inc_round(lv)` 返回值没赋给 `rnd`** → 返回的 round 字段仍是旧值 5 → auto_loop 的 `status['round'] >= MAX_ROUNDS`（L759）判 5<6 不触发 → 该关永远留在 pending，不标改关卡。
- L119 碰巧正常（初始 _rounds 遗留 1 + 6 次 inc = 7，判定时读到 6）——**不要被"另一关正常"迷惑**。

## 修复（已落地）
```python
rnd = inc_round(lv)  # 改关卡分支也要赋值
```

## 排查要点
1. **FINAL SUMMARY 有 Still pending 且轮数文件已 ≥6** → 先查 judge_with_rounds 的 round 返回值（`{round: rnd}` 里 rnd 是否等于 inc_round 返回值）。
2. `_rounds.json` 的值是"真实已跑次数"，judge 显示的 `rN/6` 是返回值——两者不一致 = 赋值 bug 或重复调用。
3. 修复后验证：改关卡分支逻辑模拟（rnd=5 → inc → 应返回 6）+ 编译 + 不污染真实 _rounds（验证脚本备份恢复）。
4. **auto_loop 结束后检查三点**：passed（待确认入库）/ failed（待确认改关卡）/ pending（=异常，应查轮数 bug）——pending 非空永远是异常信号，不是正常结果。

## 同场教训：全自动 6 轮白跑（L85/L119 案例）
- L85（目标 90，verified 顶 72.5）、L119（目标 85，verified 顶 61.8）：**verified 顶离目标 ≥17pp，6 轮探针每轮结果完全不变**（72.5/72.5/61.8/44.8/44.8 重复 6 次，combo quality 282→184 后冻结）——探针只能验证/补空缺段，**无法创造池子里不存在的胜率水平**。
- 全自动启动前先做可达性预检（见 probe-efficiency-standards 6ee）：verified 顶 < 需求段下沿 → 直接标记"待确认改关卡"，**不要浪费 6 轮批跑时间**（每轮 20-40 分钟）。
- 本次 3 关结果：L120 合格 r1 入库（88.3/88.3/60.8/49.0/49.0）；L85/L119 满 6 轮不合格 → 待用户确认改关卡。
