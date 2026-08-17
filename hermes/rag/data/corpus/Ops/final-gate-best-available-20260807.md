# Final 硬门标准 + best-available 保留 + phase1/2 噪声教训（2026-08-07）

## FinalHardGate 标准（BlastMultiTierOptimizer.cs L469-481 + L425-431）

```csharp
return gap <= FinalHardGap + 0.0001f          // gap = |PosteriorMean − 目标| ≤ 10pp
    && eval.posteriorStd <= ResolveFinalPosteriorStdMax() + 0.0001f;  // std ≤ 2.5%
```

- `FinalHardGap = 0.10f`（10pp）；`ResolveFinalPosteriorStdMax()` = min(p0阈值, p3阈值)，默认 0.025
- `PosteriorMean` 是贝叶斯后验均值，**不等于简单 WinRate**（CSV 的 RawGap 按 PosteriorMean 算，与 WinRate 差几个 pp 正常）
- **两条件必须同时满足**才是"合格"；任一不过 → final 池里 0 个 → 该档 failed

## best-available 保留（2026-08-07 用户要求："失败也要显示最接近的选项，不能就给个失败"）

**改动**（`BuildFinalResultsFromCommonPool`）：
1. 遍历 pool 时跟踪 `bestAvailable`（离目标最近的候选，即使没过 FinalHardGate）
2. 失败分支（unique.Count < perTierCount）：bestAvailable 存进 `selectionByObjective` 作 fallback，标记 `status="failed"` + `failureReason`（不合格语义不变，HasFailedTiers 仍 true）
3. 展开处自动取用 → 失败档位显示最优接近候选的实际配置 + wr，而非空白 0

**效果**：L85 案例——T1/T2 目标 90% 但关卡上限 ~80%，failed 时能看到"实际能到 80 附近"而不是 0。

## phase1/2 小样本噪声 → phase3 回归（重要判读教训）

- **L85 案例**：phase1（100局）sd=2 候选 83% → phase2（170局）81.2%（gate 通过晋级）→ phase3（320局）PosteriorMean 回归 <80% → FinalHardGate 不过 → failed
- **L136 案例**：phase2 66.5% → phase3 合并 320 局 73.13%（噪声收敛）
- **结论**：phase1/2 的 80+% 可能是小样本噪声（CI±6.5pp@200局），phase3 追加局数暴露真值。FinalHardGate 判 failed 是**正确行为**（防噪声入库），不是标准过严。用户看到"phase1 有 83% 但 summary failed"时，解释 = phase3 验证后回归，不是数据丢失（best-available 已保留最接近值）。

## leveldb 单档写入验证陷阱（write_level_db.mjs 单档改造后）

- DB entry 一直是**单档**结构（dealConfig+dealFingerprint+winRate+sourceTierLabels）；五档组合 entry（tierConfigs+tierWinRates）是旧 write_level_db.mjs 的错误设计，重构后 runStore.upsertRunEntry 要求 `boardFingerprint`+`dealFingerprint`（64位 sha256）否则返回 null
- 新流程：`readAssetSnapshot(assetPath)` 拿 boardFingerprint → 逐档 `computeDealConfigFingerprint(tier)` → 构造单档 entry → upsert（同关卡所有档 boardFingerprint 相同）
- **normal 关 T1=T2/T4=T5 同配置 → 只写 3 条独立 entry（dedup）**，write_level_db.mjs 回读验证报"部分验证失败（3/5 档）"是**验证脚本按 sourceTierLabels 找 entry 的问题**——实际按配置匹配 5/5 全对。**验证必须按 dealConfig 四元组匹配，不是按 tier label**
- 已验证案例：L128（55.5/40/33.3/25.2/9.3）、L136（77.9/77.9/73.1/50.5/50.5）、L72/79/82（四动作入库）——均按配置匹配验证通过
