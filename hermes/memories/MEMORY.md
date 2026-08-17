search_files 路径：底层 Windows 原生 rg，不支持 MSYS2 `/d/` 路径。传 `D:/path` 格式。
§
工作目录 D:\download\BlastGame\hermes，游戏工程 C:\Users\Administrator\Documents\BlastGame。reasonix 是另一个项目，忽略。
§
submit_batch_unity.py（batch mode）是唯一提交流程。旧的 submit_batch.py 已删除。不需手动 check_unity/restart_unity。
§
动手前必须 skills_list + skill_view 加载对应 skill。skill 在 Hermes 系统目录下，不能去文件夹里翻 .md 文件。
§
讨论模式下先展示方案等确认再执行。全自动模式走 auto_loop 五阶段（Warden→Planner→Bot→Judge→Curator）不等确认。
§
不猜根因、不打临时补丁。发现异常先完整展示数据对比定位问题。
§
board.md 是唯一状态源（已入库/待调优/改关卡），状态变了立即更新不等。
§
不假设已稳定运行的代码有显性 bug。排查异常先怀疑自己的操作/数据/流程。
§
被批评时直接承认改正，不找借口。先展示数据再问下一步。不要盲目同意用户，独立判断流程合理性。
§
池子数据源优先级：bot≥300 > summary≥300 > bot≥200 > summary≥200 > phase2≥200 > phase1。选不出达标组合可降级用 phase2。
§
改关卡后立即执行：清 stage-data/{lv}、从 _summary.json 移除、设 _last_refresh.json 时间防线、更新 board/timeline。
§
改关卡判断只基于最优组合（#1 combo），不基于探针数据。earlyDeath > (1-targetWR)×80% → 改关卡。
§
Phase2 CSV 列偏移：数据列 < 表头列 → 左移解读。不依赖字段值内容做判断。
§
Gap 罚分平滑连续无跳变：g<15→(15-g)×5, g<10→额外(10-g)×10。quality = target + source×0.3 + gap + death。
§
Pool 局数优先：_source_penalty = gameTier×5 + sourceRank（bot=0, summary=1, phase0=2, phase2=3, phase1=4）。
§
改关卡门槛：跑满 6 轮探针仍无合格组合时才问。差≤5pp 不是改关卡，是先搜池子→设计探针→继续调。
§
Asset 文件在 test/ 下按分段子目录存放（61_80/81_100/101_120/...），不在根目录。asset_patcher.py _asset_path 已添加 os.walk 查找。judge_level/postcheck/preflight 均已同步更新子目录查找。
§
不要轻易判断外部数据来源新旧——被纠正过把新版优化器数据说成旧版。不确定时问用户或直接对比数据。
§
asset_patcher.write_ddc已加validate_tiers校验——检查sc与ratios数量是否匹配。
§
Unity AssetDatabase.Refresh() 不加 ImportAssetOptions.ForceUpdate 不够强力——Python write_ddc 写 asset 后 Unity batch mode 可能读到旧缓存。修复：BlastBotJenkinsBatchEntry.cs 第77行改为 AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate)。
§
bug 排查铁则：以前能跑现在不能跑，一定是我改动导致的——必须以 git diff 为基准逐个检查我的修改，找到因果关系，不能瞎猜、不能删东西试图"修"。
§
submit_batch_unity.py 的 UNITY_EXE 不能硬编码版本号。项目版本从 ProjectSettings/ProjectVersion.txt 动态读取。
§
禁止操作 Unity 项目核心文件：.meta 文件、Library/（含 PackageCache/ScriptAssemblies 等）、Packages/packages-lock.json、manifest.json。这些是 Unity 数据库，损坏后 batch mode 无法自动恢复。修改只允许 .asset 文件的 DDC 配置段（通过 write_ddc）。
§
当 Unity batch mode 报错时，优先检查 Unity.exe 是否已经在运行（tasklist | grep Unity.exe）。'An error occurred while resolving packages' 可能是 'another instance running' 的误导性报错，不是真正的包问题。
§
Unity C# 编译修复（2026-07-30）：UISettingsView.cs 缺少 `using BlastGame;` 导致 `UISaveProgressView` 类型找不到。已添加该 using 指令。
§
Ratios 是比例关系不是绝对值。改 ratio 只调各段比例，不纠结具体数值。1,1,1,1,1=2,2,2,2,2=5,5,5,5,5。
§
用户要求展示数据时先给完整 markdown 表格（含原始 WR 数值含 sd/sc/ratios/of 四参数），再给差异分析。不要只给差异值省略原始数据。表格用 markdown 标准格式（| 分隔）。
§
2026-07-29 铁则强化：1) 先展示完整数据表格(含sd/sc/ratios/of四参数)再说话，不给结论不给数据是严重错误。2) 先给方案等确认再执行，不准跳过直接动手。3) 不准让用户干具体操作。4) submit_batch_unity会从probe_configs.json覆盖asset——改asset必须同步改json。
§
2026-07-29 铁则强化 #2：严禁未经允许执行任何破坏性操作 — 删文件/目录(Library/PackageCache/.meta/stage-data/assist/ref等)、修改数据库、覆盖配置。必须展示方案获得用户明确许可后才能动手。
§
funnel_b/ 是竞品关卡数据，和 test/ 完全不是一套东西。两个文件夹的同编号关卡不是同一个关卡。绝不能用 funnel_b 的数据修复 test/ 的文件。
§
池子数据结构：bot数据→{lv}.bot.json，optimizer/phase2/summary→{lv}.assist.json，phase1→{lv}.ref.json。pool.get_all_records()自动合并bot+assist，但优化器用visible_greedy策略的WR偏高，不能跟scoring_opt_vg的bot数据混用——会导致find_best_monotonic选错误组合。
§
数据展示：markdown表格(|)、含难度/四参数(sd/sc/ratios/of)、原始WR不差值、Normal合并T1=T2/T4=T5。先表后分析。
§
多档优化器（Unity BlastWorkbenchWindow.MultiTierOpt）各档独立搜最高 WR，不关心档间差。入库时人工检查档差审美。
§
核心工具：find_best_monotonic在tools.data.pool里，用get_bot_records()+dedup_records()取纯bot数据传入。不手动写选取逻辑。Fallback用_bucket不看tier标签。
§
Excel真源：lv_win_config_test.xlsx=目标胜率，手动挑配置记录.xlsx=入库记录。1.0=100%WR，空of=0。外部数据不入Excel。入库前必须bot 400局验证。
§
展示数据前必须确认来源时间。改关卡后时间防线过滤旧数据，但 phase0/phase1/phase2 数据可能来自旧关卡设计，不能直接用于新关卡判定。先查 optimizer 是否有新 summary，再查 pool 数据的时间戳。
§
filter_verified铁则：入库决策必须先调。通过: bot/summary/phase0任意局数。拒绝: phase1/phase2必须先bot 400局验证。
§
asset 写入后必须 verify_asset 验证四元组 (sd/sc/ratios/of)，不是只看 sd。write_ddc 已有写后回读+回滚，apply_probes 和 submit_batch_unity 也要在操作前后校验。probe_configs.json 是独立配置源，通过 apply_probes.py 写入 asset，submit 不再碰 asset。
§
【铁则】绝对禁止执行任何 git 命令：git checkout / git reset / git clean / git restore / git commit / git push / git pull / git stash / git add / git merge / git rebase / git revert。只读命令（git status / git log / git diff）也不行。git 操作全部由用户通过 SourceTree 手动执行。
§
全自动流程（auto_loop.py编排 2026-07-31）：Warden(8项)→Planner→apply_probes→bot→Judge(三态+6轮)→合格/接近入库、不合格r+1、r≥6改关卡。出问题自愈。不用manual submit_batch_unity。
§
探针设计原则：全部5槽用上，不留空槽。phase2验证时多放候选并行跑，不试单候选。
