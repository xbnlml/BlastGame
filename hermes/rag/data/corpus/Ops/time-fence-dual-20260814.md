# 双时间防线（2026-08-14 用户定稿）

> 用户澄清：时间防线有 **两个独立维度**，各自过滤数据，不要混成一个概念。

## 维度一：asset 牌面版本（已有机制）

- 记录什么：每关 asset 的 mtime / asset_updated_at（`stage-data/_last_refresh.json`）
- 过滤什么：牌面/关卡配置改过之后，旧牌面跑的批次数据整关作废
- 触发：改关卡时自动（write_ddc 写后恢复 mtime）+ retire_level 手动防线
- 实现：`dump_level_pools.py` 读 asset mtime 生成 `min_mtime_map`，批次目录时间 < 该值 → 该关跳过

## 维度二：机器人逻辑版本（2026-08-14 新增）

- 记录什么：机器人引擎（bot 批跑 + 多档位优化器共用）逻辑改动时刻
- 过滤什么：逻辑改动前所有批次数据（bot + multi-tier-opt 同时作废），**永久生效，不复用**
- 实现：`get_level_pool.py` 新增 `LOGIC_VERSION_SINCE` 常量 + `_logic_since_timestamp()`，
  `read_bot_attempts` / `read_opt_data` 的批次循环开头 `if batch_mtime < logic_ts: continue`
- 改动逻辑后只改这一个常量 + 重跑 `dump_level_pools.py`，池子自动只留新数据

## 组合逻辑

```
批次可用 = 批次时间 ≥ 机器人逻辑版本防线（全局一次性）
         AND 批次时间 ≥ 该关 asset 牌面防线（按关）
```

- 机器人防线管"机器人逻辑换了，老数据作废"（全局）
- asset 防线管"关卡牌面改了，旧牌面数据作废"（按关）
- 两层独立、永久生效；验证时两批目录时间分别对比防线时间戳

## 实测（2026-08-14）

- 机器人防线 08-13 14:36（北京时间）→ multi-tier-opt 只剩 08-13 15:27 批次（38 个旧批次全作废）、bot 全作废
- 池子可靠 3828→806 条；时间分布只剩 08-13/08-14
- 关键验证：08-13 批次 vs asset 防线 0 关被误过滤（该批次跑的 asset 都是当时的）
