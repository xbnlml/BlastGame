# 关键词总表（文字 → module-index）

用途：仅处理“只有功能描述、没有文件、符号、报错、配置值或交接文档”的任务；先用本表锁定索引文件，再进对应页的「快速定位」表找类/方法。
规则细则仍在 `Doc/MainGame/*_Logic.md`，本表不写实现。

明确编译错误、异常、堆栈、文件路径、类名、方法名和调用关系不得经过本表，也不因本表触发业务 Skill。

## 怎么用

1. 从用户话里提取中文/英文关键词
2. 在本表命中一行 → 打开右侧 `module-index` 文件
3. 在该文件「快速定位」表落到类/方法
4. 需要口径时再读专题文档

## 总表

| 关键词 / 同义 | 优先打开 | 专题（可选） |
|---|---|---|
| 体力 / 进关体力 / 扣体 / 回体 / 无限体力 / 补体 / 广告券 / 金币 / 扣金币 / 花金币 / 等级 / 道具库存 / Profile 同步 / 首登 | [user-module.md](user-module.md) | [Player_Data_Logic.md](../Player_Data_Logic.md) |
| 金币通胀 / 数值膨胀 / 阶段系数 / 动态定价 / CoinEconomy / 缩放金币 | [common.md](common.md) | [Coin_Economy_Logic.md](../Coin_Economy_Logic.md) |
| Top 栏 / 大厅 / 主界面 / 体力弹板 / 个人资料 / 头像 / 设置 / 音效 | [home-module.md](home-module.md) | Player_Data（体力相关） |
| 弹板顶栏 / Topbar / CoinNumObj / LifeNumObj / AdNumObj / GamePanelConfig | [common.md](common.md) / [game-main-ui.md](game-main-ui.md) | [Win_Settlement_UI.md](../Win_Settlement_UI.md) |
| Top 栏 / 大厅 / 主界面 / 体力弹板 / 个人资料 / 头像 / 设置 / 音效 / 存档登录 / 删除账号 | [home-module.md](home-module.md) | Player_Data（体力相关） |
| 震动 / 触感 / Nice Vibrations / GameHaptic / HapticSwitch / 试震 | [home-module.md](home-module.md) | [Nice_Vibrations_Haptic_Logic.md](../Nice_Vibrations_Haptic_Logic.md) |
| 底栏 / BottomUIView / 底部导航 / HomeModule 页签切换 | [home-module.md](home-module.md) | [BottomUIView_Refactor.md](../BottomUIView_Refactor.md) |
| 14天签到 / 每日签到 / Daily Delivery / 里程碑宝箱 / 广告补签 | [daily-delivery-module.md](daily-delivery-module.md) | [Daily_Delivery_Logic.md](../Daily_Delivery_Logic.md) |
| 新手签到 / 7天签到 / Grand Opening / 终点大奖 | [grand-opening-week-module.md](grand-opening-week-module.md) | Daily_Delivery_Logic（GOW 部分） |
| 通行证 / Pass / 加星 / 循环奖励 / 付费奖励 | [game-pass-module.md](game-pass-module.md) | [Game_Pass_Logic.md](../Game_Pass_Logic.md) |
| 引导 / 剧情 / 打字机 / 手势引导 / 挖洞 | [guide-module.md](guide-module.md) | `Doc/GuideModule/GuideModule_Implementation.md` |
| 回放 / Replay / 录制回放 | [game-main-runtime.md](game-main-runtime.md) | [Blast_Replay.md](../Blast_Replay.md) |
| 进关 / 加载关卡 / 胜负 / 中途退出 / 主流程 | [game-main-runtime.md](game-main-runtime.md) | [Gameplay_Flow_Logic.md](../Gameplay_Flow_Logic.md) |
| Slot 区 / 临时槽 / 槽位 close / 槽位压缩 / runtimeId | [game-main-ui.md](game-main-ui.md) | [Slot_Area_Logic.md](../Slot_Area_Logic.md) |
| 复活 / 失败续命 / FailOffer / Play On Offer / 复活礼包 / 续命 IAP | [game-main-runtime.md](game-main-runtime.md) / [user-module.md](user-module.md) | [Fail_Revive_Logic.md](../Fail_Revive_Logic.md) / [PlayOn_Offer_Logic.md](../PlayOn_Offer_Logic.md) |
| 攻击 / 特殊块 / 下落补块 / 队列 | [game-main-sim.md](game-main-sim.md) | [Gameplay_Rules_Logic.md](../Gameplay_Rules_Logic.md) |
| Stage 点击 / 连点门控 / 拒点 / 放置流解锁 | [game-main-runtime.md](game-main-runtime.md) / [game-main-sim.md](game-main-sim.md) | [Stage_Animal_Animation_Playback.md](../Stage_Animal_Animation_Playback.md) / [GM_Board_Stage_Flow.md](../GM_Board_Stage_Flow.md) |
| 开局参数 / 动态难度 / 洗牌 | [game-main-level-core.md](game-main-level-core.md) | [Level_Entry_Init_Logic.md](../Level_Entry_Init_Logic.md) |
| 道具锤 / 法杖 / PowerUp 使用 | [game-main-runtime.md](game-main-runtime.md) | [POWERUP-SYSTEM-Unity.md](../POWERUP-SYSTEM-Unity.md) |
| 得分 / 连击 / HUD 反馈 | [game-main-ui.md](game-main-ui.md) / runtime | [Game_Score_Logic.md](../Game_Score_Logic.md) |
| 飞金币 / 多币飞 / 结算飞币 / UiRewardMultiCoinFly | [common.md](common.md) / [game-main-ui.md](game-main-ui.md) | [Win_Settlement_UI.md](../Win_Settlement_UI.md) / [Common_Runtime_Infrastructure.md](../Common_Runtime_Infrastructure.md) |
| 通用奖励弹窗 / CommonRewardView / RewardTitleType / 奖励排列 / 奖励标题图 | [common.md](common.md) | [Common_Runtime_Infrastructure.md](../Common_Runtime_Infrastructure.md) |
| 反向遮罩 / 贴图挖洞 / 点穿 / InverseTextureMask / 贴图 alpha 遮罩 | [common.md](common.md) | [Common_Runtime_Infrastructure.md](../Common_Runtime_Infrastructure.md) |
| 棋盘背景 / GridRoot / ui_bg / 难度底图 | [game-main-ui.md](game-main-ui.md) | — |
| TMP 描边 / 字体材质 | [common.md](common.md) | — |
| Bot 仿真 / Bot 决策 / 自动跑局 / 单局模拟 / Bot 批跑 / 胜率评估 / 关卡评估 / Beam 决策 / 死局诊断 / 对拍 / 优化器 | [editor.md](editor.md) | `Doc/Bot/Bot_Architecture.md` |
| 打包 / Jenkins / 二维码 | [buildpackage-tools.md](buildpackage-tools.md) | — |

## 易混词

| 用户说法 | 不要先去 | 应去 |
|---|---|---|
| 每日签到 / 14天 | grand-opening-week | daily-delivery-module |
| 新手签到 / 7天 | daily-delivery | grand-opening-week-module |
| 体力规则 | 只改 Home UI | user-module + Player_Data_Logic |
| 体力 HUD 展示 | 只改 UserModule | home-module + user-module |

## 维护

- 新增高频中文说法时，先加本表一行，再补对应模块「快速定位」表。
- 不要在本表展开方法细则。

## AI 提示词路由

| 提示词 / 用户意图 | 第一入口 | 第二步 |
|---|---|---|
| “主流程怎么走 / 一局如何推进” | `game-main-runtime.md` | `Gameplay_Flow_Logic.md` |
| “为什么不能点击 / 放置后怎么合成” | `game-main-runtime.md` / `game-main-sim.md` | `Gameplay_Rules_Logic.md` |
| “回放从哪里开始 / 为什么回放分叉” | `game-main-runtime.md` | `Blast_Replay.md` |
| “关卡进入时参数从哪里来” | `game-main-level-core.md` | `Level_Entry_Init_Logic.md` |
| “攻击、特殊块、队列、下落怎么处理” | `game-main-sim.md` | `Gameplay_Rules_Logic.md` |
| “Board / Stage / Slot 画面如何刷新” | `game-main-ui.md` | `GM_Board_Stage_Flow.md` |
| “Bot 和 Runtime 为什么不一致” | `Doc/Bot/Bot_Runtime_Slot_State_Parity.md` | `Doc/Bot/Bot_Architecture.md` |
| “某个类在哪 / 文件职责是什么” | `gamemain-class-function-index.md` | `module-index/*` |
| “工具或 Editor 菜单在哪里” | `editor.md` | 对应 `Assets/GameModule/Editor/` 文件 |

## 按文件反查

- 看到 `BlastGameController*.cs`：先看 `game-main-runtime.md`，再按 partial 名称进入 `Gameplay_Flow_Logic.md` 或 `Blast_Replay.md`。
- 看到 `BlastGameLevelSession.cs` / `BlastLevelEntry.cs`：先看 `game-main-level-core.md`，再看 `Level_Entry_Init_Logic.md`。
- 看到 `BlastGameLogic.cs` / `BlastAttackSystem*.cs` / `BlastEngine.cs`：先看 `game-main-sim.md`，再看 `Gameplay_Rules_Logic.md`。
- 看到 `BlastGameViewPresenter.cs` / `BlastStageView.cs` / `BlastSlotsView.cs`：先看 `game-main-ui.md`，再看 `GM_Board_Stage_Flow.md`。
- 看到 `BlastBot*.cs`：先看 `Doc/Bot/Bot_Architecture.md`，规则一致性再看 `Bot_Runtime_Slot_State_Parity.md`。

索引只负责回答“去哪里看”；不要为了查入口读取整个专题文档。
