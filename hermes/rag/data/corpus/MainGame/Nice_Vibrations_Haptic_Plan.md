---
name: NiceVibrations SO 接入
overview: 已落地为正式专题 Doc/MainGame/Nice_Vibrations_Haptic_Logic.md。GameHapticManager 独立于 SDK HapticModule；仅 Preset + Tone。
todos:
  - id: asmref
    content: HotUpdate.asmdef 引用 Lofelt.NiceVibrations
    status: completed
  - id: so-model
    content: Catalog SO；Mode 仅 Preset|Tone（amp/freq/duration/次数/间隔）
    status: completed
  - id: player
    content: GameHaptic：Play(id)/PlayPreset/PlayTone + 冷却连震；Tone 按时长分流
    status: completed
  - id: manager
    content: GameHapticManager 独立管理器（不改 HapticModule）
    status: completed
  - id: gm-test
    content: GM「震动NV」：Preset/Tone 试播、复制 JSON、Catalog 剪贴板导入
    status: completed
  - id: doc-sync
    content: Doc：Nice_Vibrations_Haptic_Logic.md + keyword-map
    status: completed
isProject: false
---

# Nice Vibrations 接入（计划已收束）

**实现真源**：[Nice_Vibrations_Haptic_Logic.md](../MainGame/Nice_Vibrations_Haptic_Logic.md)

本文件仅保留范围备忘；细则以 Logic 文档为准。

## 范围

| 做 | 不做 |
|---|---|
| Preset + Tone + Catalog SO | Advanced Clip / Curve / 自定义 Clip |
| `GameHapticManager`（不用 SDK HapticModule 管 NV） | 24 场景默认表 |
| 冷却/连震 + GM 试震 + 复制 JSON 回写编辑器 | 批量改玩法调用点 |
