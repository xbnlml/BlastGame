# UIEffect 项目使用约定

> **AI 使用提示**：处理 UIEffect、UI 特效、预设或材质接入时读取本文；只遵循项目使用边界，不把本文当作第三方完整 API 手册。

## 适用范围

只记录项目使用 UIEffect 时的入口和限制，不维护第三方库完整 API。

## 使用链路

```text
UI View
  → UIEffect / UIEffectTweener
  → preset / material
  → show / hide / tween
```

- UIEffect 只负责视觉效果，不承载玩法状态。
- 预设和材质由资源配置管理，业务代码不复制效果参数。
- 动态创建 UI 时，在 View 生命周期内绑定并在销毁时解除。
- 同一效果需要多个对象同步时，优先使用项目已有封装。

## 项目代码入口

- 运行时调用：搜索 `UIEffect`、`UIEffectTweener` 和对应 View。
- 预设绑定：查看具体 Prefab 和其 View/Binder。
- 统一动画编排：`BlastUiAnimExecutor`。
- 局内特效：`BlastEffectsView`。
- Stage / Slot 动物动画：`Stage_Animal_Animation_Playback.md`。

## 排查顺序

1. 确认组件和预设是否绑定。
2. 确认调用发生在 View 有效生命周期内。
3. 确认效果是否被重复绑定或重复播放。
4. 确认材质、Shader 和 Canvas 层级。
5. 最后检查具体第三方参数。

本文不记录一次性效果调试过程；需要细节时直接从调用点进入当前组件或 Prefab。
