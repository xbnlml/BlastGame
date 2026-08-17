# 多档位优化器 Final 诊断 + 入库 DB 单档写入（2026-08-08）

> 本文件补充 multi-tier-phase1-sampling-redesign-20260807.md 未覆盖的 Final 阶段 + 入库 DB 侧经验。
> 场景：读多档位批次 summary / phase1-3 数据判断"为什么 failed"、入库时同步关卡数据库。

## 1. phase1/2 的 80+ 胜率可能是噪声，phase3 追加后回归（L85 案例）

- **现象**：L85（目标 90/90/75/60/60）summary 里 T1/T2 failed（wr=0），但 phase1_raw 有 83%（sd2/10,10,1,10,10）、phase2 有 81.2%（170局）。
- **根因**：phase1/2 是 100-170 局小样本，80+ 是噪声偏高；phase3 追加到 320 局后 `PosteriorMean` 回归（真实 <80%），`FinalHardGate`（gap=|μ−目标|≤10pp 且 posteriorStd≤2.5%）不过 → final 池 0 个合格 → failed。
- **结论**：final 判 failed 是**正确**的可靠性防线（防小样本噪声冒充合格入库），不是 bug。用户看到 phase1/2 的 80+ 会问"为什么 failed"——根因是 phase3 噪声收敛，不是采样不够。
- **同型案例**：L136 phase2 66.5% → phase3 73.13%（噪声收敛到真值）。

## 2. Final 失败应保留 best-available（最优接近候选），不能直接给 0

- **用户纠正**："失败也要显示最接近的选项啊，不能就给个失败"。
- **改动**（BlastMultiTierOptimizer.cs `BuildFinalResultsFromCommonPool`）：
  1. 遍历 pool 时跟踪 `bestAvailable`（离目标最近的候选，即使没过 FinalHardGate）。
  2. 失败分支（`unique.Count < perTierCount`）：bestAvailable 存进 `selectionByObjective` 作 fallback，标记 `status="failed"` + `failureReason`。
  3. 展开处自动取用 → 失败档位显示实际能达到的配置 + wr（如 L85 T1 显示 ~79-81% 而非 0）。
- **语义保持**：`HasFailedTiers=true` + failureReason 不变——只是展示层补了"实际能到多少"，不改"不合格"判定。

## 3. 多档位数据新旧批次区分（池子可能没含最新批次）

- 查某关多档位胜率覆盖时，**先确认池子(`get_all_records`)是否已含最新批次**——池子只在 dump 时更新，若批次在 dump 之后跑完，池子里只有旧 bot 数据（如 54/57/83 只有 07-08~07-14 的 bot，没有 08-07 phase1/2）。
- **正确做法**：直接读 telemetry 原始 CSV（`{批次}/{lv}-{ts}/phase1_raw.csv` + `phase2_candidates.csv`），按配置四元组 (sd,sc,ratios,of) 去重（phase2 优先），看胜率范围。
- phase1_raw 的胜率列是 `WinRate`；phase2_candidates 的胜率列**也是 `WinRate`**（不是 `VerifiedWinRate`——后者恒 0 会误读成"全 0%"）。

## 4. 关卡数据库是单档 entry 结构；write_level_db.mjs 已改单档写入

- **DB 结构**：`LevelDatabase/Run/test.json` 每档一条 entry（`dealConfig` + `dealFingerprint` + `winRate` + `sourceTierLabels`），**不是五档组合 entry**。全库 1038 条全单档。
- **write_level_db.mjs 改造（2026-08-07）**：从"五档组合 entry（tierConfigs + computeTierConfigFingerprint）"改为"逐档单档 entry"：
  - 每档 `computeDealConfigFingerprint(tier)` 算 dealFingerprint（`tools/leveldb_sync/` 下工具用新 API）。
  - `boardFingerprint` 从 asset 读（同关卡所有档相同），`readAssetSnapshot(assetPath)` 一次返回 board+tiers+fingerprints。
  - 每档独立 `upsertRunEntry`，保留分档修改记录。
  - 输入仍是五档 payload（tierConfigs[5] + tierWinRates[5]），输出拆成 5 条单档 entry。
- **验证**：L128/L136/L102/L54/L61 等已用此流程写 DB 成功。normal 关 T1=T2/T4=T5 同配置会被 dedup 成 3 条独立 entry，回读验证报"3/5 档"是**正常**（按配置匹配 5/5 都对），不是写入失败。

## 5. DB 新旧同配置 entry 并存：验证入库必须过滤 sourceFileName

- 某关同配置可能既有旧数据（campaign-summary 老批次，wr 变）又有新入库（reimport-YYYYMMDD）——**DB 里两条同配置 entry 并存，前端按最新匹配**。
- 验证入库 DB 匹配时，**只认 `sourceFileName` 含 `reimport-*` 的新 entry**，否则会匹配到旧 campaign-summary 的 wr（如 L54 T3 旧 0.359 vs 新 0.512，误报失败）。

## 6. 改关卡信号（确凿）

多档位批次某关 failed 且 reason 为"Phase1/Phase2 档位 X 交叠门内唯一候选仅 0 个(目标 Y)"→ **该关配置根本达不到目标 Y**（如 119/120/138/144 目标 85 段门内 0 候选；57/93 目标 90 最高才 55-65%）→ 确凿的**改关卡**信号，不是采样不足。