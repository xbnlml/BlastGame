# 多档位优化"跑得比以前慢"排查方法论（2026-08-07）

> 现象：L110 单关跑 28 分钟还在 phase1。用户："以前 sample100 也没这么慢！我说了然你看以前的逻辑！别再扯其他的了"

## 用户纠正（铁则）

1. **下结论前先看旧机制/旧代码**——禁止凭记忆猜"以前是 X"。本会话错误示范：猜"以前 phase1 只跑 16 候选"，实际旧机制是 R1a 16 锁 sd20 + extension/R2 补洞共 71 候选（8-03 批次 phase1_raw 71 行）
2. **用户明确要求对比新旧代码时，git diff（只读）可用**——memory 禁 git 铁则的例外：用户说"用 sourcetree 都能看新老差距"即授权只读 git diff（`git diff <file>` 不写任何东西）
3. 用户说"看以前的代码"就去看（git diff / 历史批次数据），别辩解"没有备份"

## 正确排查路径（按顺序）

1. **对比历史批次 manifest**：`run_manifest.json` 的 Phase1Samples/Phase1Runs/Phase2Runs/Phase2AdvancePerTier 是否变了（本案例：全同=参数没变，是代码变了）
2. **对比历史批次 phase1_raw 候选数**：`wc -l <批次>/<关>-*/phase1_raw.csv` —— 8-06（改前）=32 行 vs 现在（改后）=99 候选 → **3.1 倍**是根因
3. **git diff 看新旧代码**：`git diff Assets/GameModule/Editor/Bot/BlastMultiTierOptimizer.cs BlastMultiTierPhase1AdaptiveSampler.cs` —— 本案例根因：R1a `Round1PresetCount=16`(锁sd20) → `Round1TotalPresetCount=75`(5sd×15ratios) + R1b 深度 2→5
4. **看 Unity Editor.log 实时进度**：`grep "Cumulative" Editor.log | tail` 显示 `sample N/100, round1 sd=X preset Y/15` —— 能确认卡在哪个阶段、累计局数
5. **每候选耗时估算**：从批次开始到日志当前局数 ÷ 局数 × 100 = 每候选秒数

## 陷阱

- **manifest/summary 统一时间戳是假象**：批跑启动时统一生成所有关的 manifest（时间戳相同），不能用来判断单关耗时；要看各阶段文件（phase0_prior.csv/phase1_raw.csv）的 mtime 差
- **8-03 批次 25 关 10:03 同时开始 ≠ 并行**：Unity 不可并行（skill 记录），是 batch mode 串行跑、manifest 统一生成
- **phase0 贝叶斯提前停**：`StopReason="early:threshold"`、TotalRuns=200 < PlannedRuns=400 —— 以前 phase0 能省一半局数，排查耗时别只看候选数
- **phase1 总预算**：`sampleSoftCap = phase1Samples = 100`（L745），R1a/R1b/R2 共享 100 个候选槽 × 100 局 = 10000 局上限

## 本案例结论

phase1 候选 32→99（R1a 16 锁sd20 → 75 全sd 覆盖 + R1b 深度5），每候选 100 局不变 → 耗时 17 分钟 → 40 分钟（~2.5 倍）。这是 R1a 重设计"覆盖更广"的代价。缓解选项：减 R1a 候选（5sd×10ratios=50）、R1b 深度 5→3、phase1 局数 100→60（phase2 再验证）。
