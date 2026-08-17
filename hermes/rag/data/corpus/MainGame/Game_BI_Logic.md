# Game_BI_Logic（专题）

## 模块定位

- 本文维护 Blast 玩法 BI 的专题口径：事件映射、字段定义、默认值与边界约束。
- 主文档 `Doc/MainGame/Blast_MainGame.md` 仅保留模块入口与短摘要，不重复展开细节。

## 类功能定位

- `BlastGameLevelPlayBIEventNames`
  - 角色：玩法 BI 事件名常量入口。
  - 文件：`Assets/GameModule/GameMain/Script/Runtime/BlastGameLevelPlayBIModels.cs`
- `BlastGameLevelPlayBI*Data`
  - 角色：玩法 BI 独立数据模型（按事件拆分），不复用回放 record。
  - 文件：`Assets/GameModule/GameMain/Script/Runtime/BlastGameLevelPlayBIModels.cs`
- `BlastGameLevelPlayBIPayloadBuilder`
  - 角色：按事件组装 BI 字段字典 payload（字段名与文档口径一致）。
  - 文件：`Assets/GameModule/GameMain/Script/Runtime/BlastGameLevelPlayBIModels.cs`

## 字段口径

- 坐标：回放 0-based；BI 上报 1-based（无值记 0）。
- 布尔：统一映射 `int`（`0/1`）。
- 难度：`sd` 为动态难度档位，限定 `1~5`；无动态档时上报中性档 `3`。
- 分组：`level_group` 读取玩家当前关卡分组；当前为 `funnel_b` 或 `test`，缺省回退 `funnel_b`。
- 缺省值：`int` 为 `0`，`string` 为空串。
- `company_user_name`：内部测试玩家标识；由 GM「设置测试用户名」写入本地 `PlayerPrefs`，`BlastGameBI.TrackEvent` 每次上报时读取并统一附带，不参与服务器资料同步。

## 事件映射（当前）

- `place_slot`：放置成功后上报，字段取放置后状态（含 `is_merge`、`slots_total`、`slots_taken`）。公共字段为 `level`、`sd`、`level_group`。
- `load_level`：关卡加载及首轮布局稳定后上报。
- `reward_level`：普通领取、双倍领取或重启后的未领取补领完成后上报。
- `prop_purchase`：道具购买成功后上报；道具 5 为即买即用。
- `prop_use`：道具实际使用成功后上报。
- `fail_revive`：复活相关流程上报（点击/结果按业务入口区分）。
- `end_level`：结算弹板出现时上报。

## 字段明细

| 字段 | 含义 | 适用事件 |
|---|---|---|
| `level` | 当前关卡编号，最小为 `1` | 全部 |
| `sd` | 动态难度档位，范围 `1~5`；无动态上下文时为中性档 `3` | 全部 |
| `level_group` | 玩家当前关卡分组，通常为 `funnel_b` 或 `test` | 全部 |
| `company_user_name` | GM 设置的内部测试用户名；未设置为空串 | 全部 |
| `col` | 放置位置列号，BI 为 1-based；无位置为 `0` | `place_slot` |
| `row` | 放置位置行号，BI 为 1-based；无位置为 `0` | `place_slot` |
| `delta_ms` | 距上一次成功放置的时间间隔，单位毫秒；首次为 `0` | `place_slot` |
| `slots_total` | 放置后的槽位总数 | `place_slot` |
| `slots_taken` | 放置后的已占用槽位数 | `place_slot` |
| `is_merge` | 本次放置是否触发合并，`1` 是、`0` 否 | `place_slot` |
| `is_tap` | 本次操作是否为点击；当前放置链路固定为 `1` | `place_slot` |
| `use_boost` | 道具编码：`0` 无、`1` 磁铁、`2` 魔杖、`3` 锤子、`4` 回退 | `place_slot` |
| `lives` | 上报时玩家当前生命数 | `load_level`、`end_level` |
| `load_time` | 本次加载入口至首轮布局稳定、派发 UI Ready 的真实耗时（毫秒）；首次进入包含 View 分帧预热 | `load_level` |
| `cycle` | 当前关卡尝试次数，取 `currentLvLoseStreak` | `reward_level` |
| `remain_prop1` ~ `remain_prop4` | 1~4 号库存道具剩余数量 | `load_level`、`reward_level`、`prop_purchase`、`prop_use` |
| `level_stars` | 本关获得星数 | `reward_level` |
| `remaining_stars` | 领奖后的剩余星数 | `reward_level` |
| `gain_stars` | 本期累计获得星数 | `reward_level` |
| `normal_claim` / `double_claim` | 普通/双倍领取标记，`0/1`；重启补领按普通领取 | `reward_level` |
| `prop_type` | 道具编号，支持 `1~5` | `prop_purchase`、`prop_use` |
| `tap_position` | 使用道具时点击入口传入的位置/块 ID | `prop_use` |
| `progress` | 复活时关卡清除进度，格式为 `已清除/目标总数` | `fail_revive` |
| `is_revived` | 本次复活是否成功，`1` 成功、`0` 失败 | `fail_revive` |
| `coin_now` | 复活处理时玩家当前金币数 | `fail_revive` |
| `coin_cost` | 本次复活所需或消耗的金币数 | `fail_revive` |
| `is_win` | 本局是否胜利，`1` 胜利、`0` 失败 | `end_level` |
| `win_count` | 本次结算后的连胜数；失败为 `0` | `end_level` |
| `remaining_blocks` | 结算时剩余目标方块数 | `end_level` |
| `cleared_blocks` | 本局已清除目标方块数 | `end_level` |

## 当前代码入口（2026-05-11）

- 上报入口：`BlastGameLevelPlayBIReporter`
- payload 组装：`BlastGameLevelPlayBIPayloadBuilder`
- Runtime 挂点：
  - `LoadLevel` 成功且首轮布局稳定后：上报 `load_level`
  - Stage 放置成功后：上报 `place_slot`（按放置后状态取 `is_merge/slots_total/slots_taken`；`is_merge` 口径为主槽位 merge 或 temp-slot merge）
  - Fail-revive 确认回调：上报 `fail_revive`
  - `EnterWinState/EnterLoseState`：上报 `end_level`

## end_level 字段补充（2026-05-11）

- `win_count`：在结算入窗时按“本次结果”口径计算；胜利场景使用 `profile.winStreak + 1`，失败场景为 `0`。
- `remaining_blocks`：取 HUD 同源 remaining 口径。
- `cleared_blocks`：按 `Mathf.Max(0, remainingTotal) - remainingBlocks` 计算（与 HUD 同源）。

## 边界约束

- 回放与 BI 必须解耦：`BlastActionReplayRecorder` 只负责回放动作记录。
- BI 字段扩展优先在 `BlastGameLevelPlayBIModels` 中新增，不在 replay record 里“借字段”。

## 用户属性

- `BlastGameBI.SetUserEmail(string email)` 通过 `ServiceHub.Instance.UserSet` 上报数数用户属性 `email`。
- 仅在邮箱确认或资料同步成功后调用，不在 `ProfileBaseData.Email` setter 中调用。

### 用法

```csharp
BlastGameBI.SetUserEmail(profile.Email);
```

调用方需引用 `Betta.Common`；空邮箱会自动跳过上报。
