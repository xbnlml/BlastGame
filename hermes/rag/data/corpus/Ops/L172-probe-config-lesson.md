# L172 致命排查案例 (2026-07-29)

## 现象
- write_ddc 写了 L172 T1=sd=32/r=4,1,5/of=0.13
- 每次 bot 批跑后 asset 被覆盖回旧配置 T1=sd=36/r=4,1,6/of=0.17
- 连续 6 轮 bot 跑的都是旧配置，WR=73-80%

## 排查过程（错误路径）

1. 以为 Unity AssetDatabase 缓存 → 修改 C# 加 ForceUpdate ❌
2. 以为 Library 缓存 → 删除 Library/ArtifactDB 部分 ❌
3. 以为 .meta 文件冲突 → 删除 172.asset.meta → Unity 批跑彻底炸了（包解析失败）❌❌
4. 以为 PackageCache 问题 → 删除整个 PackageCache ❌
5. 还原 .meta 和 packages-lock.json（git checkout）✅
6. **发现根因：** `submit_batch_unity.py` 每次运行前从 `probe_configs.json` 读配置覆盖 asset √

## 真正根因
`submit_batch_unity.py` 旧版 lines 98-139:
```python
if not args.skip_patch:
    with open('tools/probe_configs.json') as f:
        pc = json.load(f)
    for lv in LEVELS:
        cfg = pc.get(lv)
        write_ddc(int(lv), tiers)  # ← 用旧配置覆盖了正确的 asset
```

L172 在 `probe_configs.json` 里是过期数据（T1=sd=36），每次 submit 都覆盖。

## 修复
- `submit_batch_unity.py` 移除全部 probe_configs 逻辑（永远 skip_patch）
- 新建 `apply_probes.py` 作为独立配置管理工具
- 配置管理（write_ddc/apply_probes）与 bot 提交（submit）完全解耦

## 教训
1. 排查配置问题时，最先查配置来源链（谁在写？什么时候写？），不是查缓存
2. 绝不要删 Unity .meta 文件
3. 外部 bot 数据策略标注不可信 — 同一四元组不同批次差 14pp+
4. 最终信任自己新跑的 scoring_opt_vg 400 局结果（L172 T1=60.8%，可信）
