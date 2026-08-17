# Blast MainGame（入口导航）

本文仅作为 `GameMain` 文档总入口，不承载实现细节与规则展开。

- 导航总入口：`Doc/Bot_MainGame_Doc_Navigation.md`
- 文档维护与迁移说明：`Doc/Doc_Migration_Report.md`
- 适用代码范围：`Assets/GameModule/GameMain/Script/`、`Assets/GameModule/GameMain/Config/`

---

## 1. 模块入口（按 Playbook 映射）

| Playbook | 模块文档 | 用途 |
|---|---|---|
| `gameplay-flow-logic.md` | `Doc/MainGame/Gameplay_Flow_Logic.md` | 关卡加载/推进/胜负/主流程（不含切场景与壳层 UI） |
| `gameplay-rules-logic.md` | `Doc/MainGame/Gameplay_Rules_Logic.md` | 攻击系统/特殊块/队列/下落补块 |
| `gameplay-replay-logic.md` | `Doc/MainGame/Blast_Replay.md` | 回放录制、播放、校验 |
| `game-score-logic.md` | `Doc/MainGame/Game_Score_Logic.md` | 计分、连击、HUD 反馈 |
| `game-bi-logic.md` | `Doc/MainGame/Game_BI_Logic.md` | 玩法 BI 字段与上报 |
| `game-analysis-logic.md` | `Doc/MainGame/Game_Analysis_Logic.md` | 运行时队列日志、性能/对拍分析 |
| `level-entry-init-logic.md` | `Doc/MainGame/Level_Entry_Init_Logic.md` | 关卡进入初始化/开局参数 |
| `game-pass-logic.md` | `Doc/MainGame/Game_Pass_Logic.md` | 通行证赛季、进度、奖励领取与循环奖励 |
| `player-data.md` | `Doc/MainGame/Player_Data_Logic.md` | 体力/金币/等级/道具与 Profile 同步 |
| `server-level-data-logic.md` | `Playbooks/server-level-data-logic.md` | 服务器关卡数据一致性 |
| `game-model-scaffold.md` | `Playbooks/game-model-scaffold.md` | 模块 Model 脚手架（Config + Profile） |
| `grand-opening-week-logic.md` | `Doc/MainGame/Daily_Delivery_Logic.md` | 新手 7 天签到（GrandOpeningWeek）——自动签到 + 最终大奖 + LoopGridView 列表 |
| `daily-delivery-logic.md` | `Doc/MainGame/Daily_Delivery_Logic.md` | 每日签到（DailyDelivery）——14 天循环签到 + 里程碑宝箱 + LoopListView2 列表 |

---

## 2. 专题入口

- 动态难度：`Doc/MainGame/Blast_DynamicDifficulty.md`
- 动态难度需求口径：`Doc/MainGame/DynamicDifficulty_FE_Requirement.md`
- 回放链路：`Doc/MainGame/Blast_Replay.md`
- 玩法规则：`Doc/MainGame/Gameplay_Rules_Logic.md`
- Stage 入槽合成门槛（`gameLevel < 3` 不触发 `3` 合 `1`）：`Doc/MainGame/Gameplay_Rules_Logic.md`
- 主流程编排：`Doc/MainGame/Gameplay_Flow_Logic.md`
- Stage Animal 动画播放：`Doc/MainGame/Stage_Animal_Animation_Playback.md`
- 场景与壳层 UI：`Doc/MainGame/Scene_And_UI_Transition.md`
- UI 框架：`Doc/Tools/UIManager_Usage.md`
- 得分与连击：`Doc/MainGame/Game_Score_Logic.md`
- 玩法 BI：`Doc/MainGame/Game_BI_Logic.md`
- 分析诊断：`Doc/MainGame/Game_Analysis_Logic.md`
- 开局初始化：`Doc/MainGame/Level_Entry_Init_Logic.md`
- 模块 Model 数据层：`Doc/MainGame/Game_Model_Logic.md`
- Common 运行时基础设施：`Doc/MainGame/Common_Runtime_Infrastructure.md`
- 新手签到专题：`Doc/MainGame/Daily_Delivery_Logic.md`（GrandOpeningWeek 部分）
- 每日签到专题：`Doc/MainGame/Daily_Delivery_Logic.md`（DailyDelivery 部分）
- 通行证专题：`Doc/MainGame/Game_Pass_Logic.md`
- 玩家数据专题：`Doc/MainGame/Player_Data_Logic.md`
- 道具系统：`Doc/MainGame/POWERUP-SYSTEM-Unity.md`
- Board/Stage 流程图：`Doc/MainGame/GM_Board_Stage_Flow.md`
- **音频/震动/铃声设置持久化**：开关值存于 `Profile.SettingData` 的 `MusicSwitch` / `SoundSwitch` / `HapticSwitch`；音效由 `AudioModule`(`IAudioSystem`) 同步到 `AudioHub`；**震动**由 `GameHapticManager` 读写 `HapticSwitch` 并同步 `HapticController.hapticsEnabled`（见 [Nice_Vibrations_Haptic_Logic.md](Nice_Vibrations_Haptic_Logic.md)）；设置页点击切换走 `SetHapticsEnabled(!IsHapticsEnabled())`。**通知/铃声开关**：显示状态从 `ServiceNotifications.IsNotificationOn()` 读取，点击打开系统通知设置。
- **视图销毁清理**：`BlastGameViewPresenter.UnbindViews()` — 见 `Doc/MainGame/Scene_And_UI_Transition.md` §5。
- **关卡中途退出**：`BlastGameController.AbandonLevel()` — 见 `Doc/MainGame/Gameplay_Flow_Logic.md` §5。
- **Home Profile（HomeModule）**：主页 `TopUIView` 新增头像/头像框展示，点击头像打开 `UIProfileView`，支持 Avatar/Frame 切换、预览、保存到现有 Profile 存储链路；昵称读取 `ProfileGameUser._UserName`（`UserName`），无值显示空。改名经 `UIChangeUserNameView` 确认后派发 `OnProfileUserNameChanged`，`UIProfileView` 订阅刷新头部。

---

## 3. 类功能索引入口

- 总纲：`Doc/MainGame/gamemain-class-function-index.md`
- 细分总览：`Doc/MainGame/module-index/game-main-agent-index.md`
- 细分页：`Doc/MainGame/module-index/game-main-runtime.md`、`Doc/MainGame/module-index/game-main-sim.md`、`Doc/MainGame/module-index/game-main-level-core.md`、`Doc/MainGame/module-index/game-main-ui.md`
- 查代码总则：`../../AGENTS.md`
- 建议路径：先看总纲，再按层进入细分页；专题问题再回专题文档。

---

## 4. 维护约定（仅导航页）

- 本文只维护“入口与边界”，不维护规则细节。
- 规则/口径调整时，更新对应模块文档；本文仅更新链接与一行用途说明。
- 资源加载统一走 `Assets/GameModule/Common/Script/ResourcesManager.cs`；业务代码不再直接调用 `ResourceHub`。
- 新增 Playbook 模块时，同步补齐本文索引与对应模块文档。
- Skill 壳入口：`Skill/README.md`（真源在 `Skill/**`）。
