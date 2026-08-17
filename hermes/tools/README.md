# BlastGame 工具索引

> **动手前必读**：做任何操作前，先看这张表找现成工具，**禁止手写脚本重复造轮子**。
> 按"你想做什么"查，不是按文件名查。工具都在 `tools/` 下，命令统一 `python tools/<工具>.py <参数>`。

---

## 一、写操作（asset / Excel / board / 关卡数据库）

| 你想做什么 | 用哪个工具 | 关键参数 |
|---|---|---|
| **统一入库落盘**（asset+Excel+board 三动作）| `reimport.py` | `--config <json> [--dry-run]` |
| **入库批次全流程**（重选→落盘→DB）| `reimport_batch.py` | `--levels X --dry-run / --apply` |
| **写 asset 配置**（DDC 四元组 sd/sc/ratios/of）| `asset_patcher.py::write_ddc` | `write_ddc(lv, tiers)` + `verify_asset` |
| **写 Excel 入库记录**（就地更新，小数格式）| `project-state/_archive/write_excel.py::write_tiers` | `write_tiers(lv, tiers)` |
| **清空 Excel 数据列**（保留行结构）| `clear_excel_data.py` | `--levels X [--dry-run]` |
| **生成关卡数据库 payload** | `gen_payload.py` | `--levels X --source <批次名> [--override]` |
| **写关卡数据库**（读 `_write_payload.json`）| `leveldb_sync/write_level_db.mjs` | 先 dryrun 再正式 |
| **改关卡数据隔离**（设时间防线）| `retire_level.py` | `--levels X` |
| **改关卡后重置轮数**（清 0 重新给 6 轮）| `reset_rounds.py` | `--levels X / --all / --list` |

## 二、只读查询 / 审计

| 你想做什么 | 用哪个工具 |
|---|---|
| **查单关完整现状**（池子/组合/判定/asset/轮次）| `level_status.py`（[注] 需从 skill 复制或 PYTHONPATH）|
| **重选最优档位 vs Excel 对比** | `compare_imported.py` |
| **已入库关三方审计**（Excel vs asset vs 池子）| `audit_imported.py` |
| **数据可靠性核验**（池子三查）| `verify_pool_data.py` |
| **对比关卡数据库 vs 池子** | `compare_level_db.py` |
| **检查 asset vs Excel vs pool 一致性** | `diff_state.py` |
| **读目标胜率表** | `read_target_wr.py` |
| **51-200 状态汇总** | `stage_status.py` |
| **全局状态快照**（一行一关）| `state_snapshot.py` |

## 三、判定 / 组合 / 分析

| 你想做什么 | 用哪个工具 |
|---|---|
| **判定关卡能否满足档位差** | `judge_level.py` |
| **找最佳单调组合** | `find_best_combo.py` |
| **参数经验知识库**（ratios/sd→WR 规律）| `param_knowledge.py` |
| **设计探针** | `design_probes.py` |
| **探针写入 asset**（过 Warden 闸门）| `apply_probes.py` |
| **对比 telemetry 快照 vs 当前 asset** | `compare_asset_snapshots.py` |
| **数据可视化** | `viz_level.py` |

## 四、批跑 / 监控

| 你想做什么 | 用哪个工具 |
|---|---|
| **提交 bot 批跑** | `scripts/submit_batch_unity.py` |
| **全自动调优循环**（探针轮 `--probe-games` 默认 200 + 贝叶斯；验证轮 `--games` 400）| `scripts/auto_loop.py` |

**局数标准（2026-08-10）：** 探针批 `--games 200 --adaptive-stop`（筛选方向）；验证批 `--games 400`（入库前精测跑满）。
| **批后分析** | `post_batch_review.py` |
| **监控 bot 完成** | `monitor_bot.py` |
| **提交前验证** | `preflight.py` |
| **操作后自检** | `postcheck.py` |
| **刷新数据池缓存** | `dump_level_pools.py` |

## 五、Agent / 安全

| 你想做什么 | 用哪个工具 |
|---|---|
| **事前安全检查闸门**（Warden W01-W08）| `warden.py` |
| **组合选取 Agent** | `agent_analyze.py` |
| **数据池管理 Agent** | `agent_data.py` |
| **入库复核 Agent** | `agent_review.py` |
| **决策编排 Agent** | `planner.py` |
| **跨轮经验积累 Agent** | `curator.py` |

## 六、打包前检查（2026-08-10 新增，打包/交付前必跑）

| 你想做什么 | 用哪个工具 |
|---|---|
| **验证 asset↔DB 一致性**（asset 每档参数 vs DB 同参数 entry winRate，`--levels` 指定/`--show` 摘要；不一致退出码 1）| `verify_asset_db_match.py` |
| **官方路径终极验证**（asset→fingerprint→resolveActiveRun→winRate，模拟打包/前端查询）| `leveldb_sync/verify_packaging.mjs` |
| **对比 asset 快照 vs 池子** | `compare_asset_snapshots.py` |

**打包前固定流程：**
```bash
python tools/verify_asset_db_match.py        # 全扫 1-200，asset 参数 = DB 胜率对应参数
node tools/leveldb_sync/verify_packaging.mjs  # 官方 resolveActiveRun 路径确认
```
（reimport.py 入库后已自动调用 verify_asset_db_match，无需手动）

---

## 铁则

1. **写操作前先 `ls tools/` + 读本表**，禁止手写脚本（gen_payload/write_tiers/reimport 都有现成）
2. **禁止内联 openpyxl/正则** 重复造轮子——Excel 用 write_tiers，board 用固定脚本
3. **生成 DB payload 用 gen_payload.py**（--levels），别手写硬编码关卡列表的脚本
4. **只读脚本验证零副作用**（跑前后哈希 Excel/board/_rounds 对比）
5. **写操作前说清影响范围**（变哪些文件/不变哪些/如何回滚）