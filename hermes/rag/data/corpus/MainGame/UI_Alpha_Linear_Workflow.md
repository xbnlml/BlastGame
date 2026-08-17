# UI Alpha Linear Workflow

Linear Color Space 下，UGUI 半透明与 Photoshop（默认 Gamma 合成）观感不一致时的接入说明。

## 根因

- 项目 Color Space = Linear（`ProjectSettings.asset` → `m_ActiveColorSpace: 1`）。
- Photoshop 默认在 Gamma 空间做 Alpha 混合；Unity Linear 在线性空间混合。
- sRGB 纹理只线性化 RGB，**Alpha 不做 Gamma 解码**。
- 症状：RGB 无明显偏色，半透明区域在 Unity 中明显更淡。
- `Alpha Is Transparency` 只做透明边缘 RGB 扩色，不能修正整体透明观感。

## 方案（共享材质曲线，非预处理 / 非独立 RT）

对暗色阴影/暗色遮罩类 UGUI Sprite，使用共享材质在采样后、乘顶点色之前，只修正纹理 Alpha：

```text
correctedA = lerp(a, 1 - pow(1 - a, gamma), strength)
默认 gamma=2.2, strength=1
```

- 仅 Linear 生效；Gamma Color Space 下直接返回原 Alpha。
- 不改 RGB，不做预乘。
- 顶点色 / CanvasGroup / DOTween 的运行时 Alpha 仍按线性倍率作用在修正后的纹理 Alpha 上，淡入淡出时序不被重映射。

## 资源

| 资源 | 路径 |
|---|---|
| Shader | `Assets/GameModule/GameMain/Effect/Shader/BlastUI_PhotoshopAlpha.shader`（`BlastUI/PhotoshopAlpha`） |
| Material | `Assets/GameModule/GameMain/Effect/Materials/BlastUI_PhotoshopAlpha.mat` |
| Always Included | `ProjectSettings/GraphicsSettings.asset` 已加入该 Shader |

材质参数：

- `_AlphaGamma`：曲线幂，默认 `2.2`
- `_AlphaStrength`：混合强度 `0~1`，默认 `1`（`0` = 关闭修正）

## 适用范围

**允许接入（需人工确认“Unity 过淡”且为暗色半透明）：**

- 使用默认 UGUI 材质的 Image
- 暗色阴影 / 暗色遮罩 Sprite

**当前已接入：**

- `BlastStageCell` 下四个静态影子 Image：
  - `shadow_stage_animal`
  - `shadow_stage_animal_big`
  - `shadow_StageCellSpecialMark_Small`
  - `shadow_StageCellSpecialMark_Big`

**禁止 / 暂不接入：**

- Spine / 粒子 / SpriteRenderer / 字体
- 发光、加法、已有自定义材质
- SoftMask 数据图、Guide 孔洞遮罩、特效 Mask 纹理
- 白色发光 / 彩色半透明（暗色曲线会过重，需另配曲线或排除）
- 全局遍历、运行时自动替换、`BlastUIWindowView` 统一挂载

## 接入步骤

1. 确认目标 Image 当前 `material == null`（默认 `UI/Default`），且视觉为暗色半透明阴影/遮罩。
2. 将 Image 的 Material 设为 `BlastUI_PhotoshopAlpha.mat`（所有目标共享同一材质实例，禁止 `new Material` / `material` 属性写实例）。
3. Play Mode 对比 Photoshop：检查 Alpha 0/1 端点、半透明梯度、浅/深背景、重叠阴影；确认无 RGB 偏色。
4. 验证 Mask / RectMask2D / SpriteAtlas / CanvasGroup·DOTween 淡入淡出仍正常。
5. 若不匹配，先调材质 `_AlphaStrength`/`_AlphaGamma`；仍不对则移除此 Image 的材质引用并回退。

## 回退

- 单对象：Image Material 置空即可。
- 整体：去掉所有引用后可删除 Shader / Material；不改 PNG、`.meta`、Color Space、URP。

## 性能与验收

- 不新增 Camera / RenderTexture / 全屏 Pass。
- 所有修正 Image 共享同一材质，利于 UI batch。
- 移动端不应出现可测帧耗回退；平台压缩（ASTC/ETC2）若放大 Alpha 色阶，优先降 strength 而非改源图。

## 相关入口

- Stage 影子生命周期：`BlastStageCellView.ApplyShadowState` / `FadeShadowOut`
- Playbook：`Playbooks/game-main/ui.md` →「Linear 半透明 / Photoshop Alpha」
- 索引：`Doc/MainGame/module-index/game-main-ui.md`
