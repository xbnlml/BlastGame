# 多 Agent 工作流设计（2026-07-30讨论）

## 背景

2026-07-30 当时的 BlastGame 全自动调优为单一 agent 串行：
```
导入池子 → 选最优组合 → 设计探针 → 跑 bot → 验证 → 待用户确认 → 入库
```
瓶颈：跑 bot（Unity 不可并行）、入库决策（单一 agent 易出错）。

## 三 Agent 分工

### Data Agent
- **职责**：纯执行，不判断
- 池子导入（dump_level_pools）
- level_sig 快照校验
- 数据清洗与去重
- 写 asset（write_ddc）
- 提交 bot 批次（submit_batch_unity）
- **输入**：指令（写哪个关、跑哪个batch）
- **输出**：执行结果 + 池子状态

### Analyze Agent
- **职责**：数据分析与建议
- find_best_monotonic 选最优组合
- 按标准判定入库
- 设计探针方案（五槽全用、sd大跨度、ratios实质差异）
- **输入**：池子数据 + Excel 目标
- **输出**：候选组合 + 入库建议 + 探针设计

### Review Agent
- **职责**：独立复核，不做分析
- 逐档验证四元组（sd/sc/ratios/of）一致性
- 逐关检查 gap 合格性
- 对比 Excel 目标 WR
- 检查 config fingerprint 不重复
- **输入**：Analyze Agent 的输出 + asset 当前状态
- **输出**：✅/❌ 判定 + 不符项清单

## 编排模式

```
用户指令
  │
  ├─ Data Agent: 刷新池子
  │
  ├─ Analyze Agent: 选组合 + 出探针
  │     │
  │     ├─ Review Agent: 独立复核（并行）
  │     │
  │     └─→ 用户确认
  │
  ├─ Data Agent: 写 asset + 跑 bot
  │
  └─ Review Agent: 验证四元组 + 判定
        │
        └─→ 用户确认入库
```

## 关键规则

- Data Agent 只执行不判断
- Review Agent 独立于 Analyze Agent 上下文
- 探针设计由 Analyze Agent 出方案，Review Agent 校验规则（sd步长、ratios差异、五槽齐全）
- 入库决策：Analyze 建议 + Review 复核 → 用户最终决定
