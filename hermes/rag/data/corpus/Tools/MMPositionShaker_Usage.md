# MMPositionShaker 参数与调用说明

> **AI 使用提示**：处理震动、`MMPositionShaker` 参数或调用方式时读取本文；先确认目标组件和调用入口，再按本文约定修改。

本文说明 `Assets/Plugins/ThirdSdk/Feel/MMFeedbacks/MMFeedbacks/Shakers/MMPositionShaker.cs` 的 Inspector 参数、运行时行为，以及统一管理类的调用方式。

## 一、运行机制

`MMPositionShaker` 按以下公式计算目标位置：

```text
目标位置 = 初始位置 + 方向 × 正弦振幅 × ShakeRange × 衰减值
```

- `Transform` 模式修改 `TargetTransform.localPosition`。
- `RectTransform` 模式修改 `TargetRectTransform.anchoredPosition`。
- 震动开始时记录初始位置。
- 普通震动在 `ShakeDuration` 结束后停止。
- 震动结束时，如果启用了恢复配置，会把目标恢复到初始位置。

## 二、Shaker Settings

| 参数 | 含义 | 使用建议 |
| --- | --- | --- |
| `Channel Mode` | 震动事件的匹配方式，可按整数 Channel 或 `MMChannel` 资源匹配。 | 通过 `MMPositionShakeEvent` 全局触发时使用；直接传入目标时通常保持默认即可。 |
| `Channel` | 整数事件频道。只有频道匹配的 Shaker 才会响应。 | 使用全局事件时，发送方和目标保持一致。 |
| `Shake Duration` | 震动持续时间，单位为秒。 | 普通 Inspector 播放时生效；管理类调用会使用调用参数。 |
| `Play On Awake` | 对象启用后自动开始震动。 | 使用管理类时建议关闭，避免对象启用时意外震动。 |
| `Permanent Shake` | 持续循环震动，不在持续时间结束时正常衰减结束。 | 只适合持续抖动；普通反馈建议关闭。 |
| `Interruptible` | 是否允许新的震动打断当前震动。 | 需要连续触发时开启；关闭后，震动期间的新请求会被忽略。 |
| `Always Reset Target Values After Shake` | 强制震动结束时恢复目标值。 | 目标可能被中断、禁用或需要严格回位时建议开启。 |
| `Only Use Shaker Values` | 忽略事件传入的时长、速度、强度等参数，只使用 Inspector 中的值。 | 使用管理类传参时建议关闭，否则传入参数可能不生效。 |
| `Cooldown Between Shakes` | 两次震动开始之间的冷却时间，单位为秒。 | 防止高频重复触发。 |
| `Shaking` | 当前是否正在震动，运行时只读状态。 | 用于调试或状态判断，不需要手动修改。 |

## 三、Target

| 参数 | 含义 |
| --- | --- |
| `Mode` | `Transform` 修改 `localPosition`；`RectTransform` 修改 `anchoredPosition`。 |
| `Target Transform` | `Transform` 模式下实际被震动的目标。为空时默认使用当前组件所在对象。 |
| `Target Rect Transform` | `RectTransform` 模式下实际被震动的目标。为空时默认获取当前对象上的 `RectTransform`。 |

截图中的配置是 `RectTransform` 模式，实际震动的是 `GuideScenarioRootView` 的 `anchoredPosition`。

## 四、Shake Settings

| 参数 | 含义 | 注意事项 |
| --- | --- | --- |
| `Shake Speed` | 正弦振动的频率参数。值越大，单位时间内抖动越快。 | 它不是目标每秒移动多少单位。 |
| `Shake Range` | 最大位移幅度。 | 值越大，抖动距离越大；最终位移还会受方向归一化和衰减曲线影响。 |
| `Oscillation Offset` | 正弦振动的偏移量，用于改变初始相位/基线。 | 常规震动保持 `0`；不需要改变起始状态时不要调大。 |

## 五、Direction

| 参数 | 含义 |
| --- | --- |
| `Shake Main Direction` | 震动方向向量。`(1, 1, 0)` 表示 XY 对角线方向，实际使用前会归一化。 | 当前管理类默认传入 `(1, 1, 0)`。 |
| `Randomize Direction` | 按 `Shake Main Direction` 和 `Shake Alt Direction` 之间随机生成方向。 | 设计上用于每次震动采用不同方向。 |
| `Shake Alt Direction` | 开启随机方向时的备用方向。 | 与主方向共同决定随机方向范围。 |
| `Randomize Direction On Play` | 每次开始震动时重新随机主方向和备用方向。 | 配合 `Randomize Direction` 使用。 |
| `Randomize Direction X/Y/Z` | 控制重新随机时是否随机对应轴。 | 例如只随机 X/Y，可关闭 Z。 |

### 当前源码注意事项

当前 `MMPositionShaker.cs` 在 `ShakeStarts()` 中会计算 `_randomizedDirection`，但 `Shake()` 实际使用的是 `ShakeMainDirection`：

```csharp
_workDirection = ShakeMainDirection + ComputeNoise(_journey);
```

因此目前 `Randomize Direction` 相关参数不会真正改变最终使用的方向；它们的设计意图如上表所述，但当前行为仍以 `ShakeMainDirection` 为准。

## 六、Directional Noise

| 参数 | 含义 |
| --- | --- |
| `Add Directional Noise` | 是否在主方向上叠加基于 Perlin Noise 的方向扰动。 | 开启后会产生更不规则的抖动。 |
| `Directional Noise Strength Min` | 各轴噪声强度的最小值。 | 按 X/Y/Z 分别控制。 |
| `Directional Noise Strength Max` | 各轴噪声强度的最大值。 | 与 Min 共同决定每帧噪声强度范围。 |

关闭时方向稳定；开启时更接近随机抖动，但会增加方向变化。

## 七、Randomness

| 参数 | 含义 |
| --- | --- |
| `Randomness Seed` | 随机种子，同时参与正弦相位和方向噪声计算。 | 固定种子可以获得更稳定、可复现的表现。 |
| `Randomize Seed On Shake` | 每次开始震动时重新生成随机种子。 | 开启后每次震动表现会略有差异。 |

## 八、One Time

| 参数 | 含义 |
| --- | --- |
| `Use Attenuation` | 是否根据时间衰减震动幅度。普通震动建议开启。 |
| `Attenuation Curve` | 震动幅度随时间变化的曲线。横轴为震动进度 `0~1`，纵轴为幅度倍率。 | 默认 `0 → 1 → 0` 表示从零开始、达到峰值、最后回到零。 |

`Permanent Shake` 开启时，当前源码会固定使用 `1` 作为衰减值，因此 `Attenuation Curve` 不会产生普通一次性震动中的淡入淡出效果。

## 九、统一管理类

文件：[`MMPositionShakerManager.cs`](../../Assets/GameModule/Common/Script/MMPositionShakerManager.cs)

### 开始震动

```csharp
MMPositionShakerManager.Shake(
    targetShaker,
    durationMilliseconds: 250f);
```

参数说明：

- `targetShaker`：目标对象上的 `MMPositionShaker` 组件。
- `durationMilliseconds`：震动时间，单位为毫秒；管理类内部会转换为秒传给 `MMPositionShaker`。
- `shakeRange`：震动强度，对应 `ShakeRange`，默认值为 `30`。
- `shakeSpeed`：震动速度，对应 `ShakeSpeed`，默认值为 `30`。
- `shakeMainDirection`：震动主方向，默认值为 `Vector3(1, 1, 0)`。
- 管理类默认关闭自动播放、永久震动、随机方向和方向噪声，开启可打断和衰减，并关闭 `OnlyUseShakerValues`。
- 管理类会要求震动结束后恢复目标位置。

如果调用方只有 `RectTransform`，可以直接传入，管理类会自动获取或添加 `MMPositionShaker`，并设置为 `RectTransform` 模式：

```csharp
MMPositionShakerManager.Shake(targetRectTransform, durationMilliseconds: 250f);
```

对应停止接口不会自动添加组件：

```csharp
MMPositionShakerManager.Stop(targetRectTransform);
```

### 停止指定目标

```csharp
MMPositionShakerManager.Stop(targetShaker);
```

### 停止当前场景所有震动

```csharp
MMPositionShakerManager.StopAll();
```

`StopAll()` 会遍历当前场景中的 `MMPositionShaker` 并调用 `Stop()`，不受各对象 Channel 配置影响，同时恢复目标位置。

## 十、推荐配置

如果主要通过管理类调用，建议：

1. 关闭 `Play On Awake`。
2. 关闭 `Permanent Shake`。
3. 开启 `Interruptible`，允许新的震动请求打断旧请求。
4. 关闭 `Only Use Shaker Values`，确保管理类传入的时间、强度和速度生效。
5. 开启 `Use Attenuation`，并使用 `0 → 1 → 0` 的衰减曲线。
6. 只需要固定对角线抖动时关闭 `Randomize Direction` 和 `Add Directional Noise`。
