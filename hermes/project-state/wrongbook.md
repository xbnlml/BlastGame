# Wrongbook

Agent 层面的错题本。记录 BlastGame 调优/探针/判级过程中的错误与正确做法。

---

## WB-007: 数据池去重键未归一化导致重复

- **日期**: 2026-07-10
- **场景**: L58 池子 sd=14/ratios=1,10,1,10,1 出现两次
- **错误**: `"0.5"` vs `"0.500"` 因字符串不同被当成两个配置
- **正确**: 去重键统一 `str(float(of))` 归一化
- **执行层**:
  - `tools/get_level_pool.py`: `_norm_of()` 已加入 dedup_pools
  - `tools/data/pool.py`: `_norm_of()` 已加入 dedup_records

## WB-008: bot 数据按批次聚合而非累加，同配置只保留最新批次

- **日期**: 2026-07-10
- **场景**: 同配置出现在多个 bot 批次中，旧数据永不覆盖
- **错误**: 旧的 `read_bot_attempts` 将所有 CSV 按配置累加 wins/total
- **正确**: 按 batch_dir 分组聚合后，同配置只保留 created_at 最新的一条
- **执行层**:
  - `tools/get_level_pool.py`: `read_bot_attempts` 三阶段 (batch聚合->config去重->结果)
  - `tools/get_level_pool.py`: `dedup_by_priority` 同优先级按 created_at 取最新

## WB-009: find_best_combo 全枚举 O(n^5) 超时

- **日期**: 2026-07-10
- **场景**: 85 条记录 5 层嵌套循环
- **错误**: 4.4B 次迭代，2 分钟超时
- **正确**: 用目标值窗口剪枝 (+-10pp -> +-50pp)，降到 <=10^5 组合
- **执行层**:
  - `tools/find_best_combo.py`: `best_monotonic` 窗口剪枝搜索
  - `tools/data/pool.py`: `find_best_monotonic` 同步改造

## WB-010（已修正）: 工作目录以 Hermes 为准

- **原记录日期**: 2026-07-10（修正于 2026-07-17）
- **原错误**: 以为 reasonix 是 agent 工作目录
- **正确认知**: `D:\download\Hermes` 是当前工作目录。reasonix 是其他 AI 工程目录，与本项目无关。所有工具/配置/规则以 Hermes 目录为准。
- **工具路径**: tools/probe_configs.json、tools/**/.py、scripts/submit_batch.py 均在 `D:\download\Hermes` 下

