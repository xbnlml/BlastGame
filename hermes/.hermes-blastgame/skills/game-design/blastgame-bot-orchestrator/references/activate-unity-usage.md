# Unity 窗口聚焦

**已弃用 — 不再可靠。** 改用 `_ForceRefresh.cs` + touch 现有 .cs + AppActivate 的三件套方案（见 level-optimizer Step 3）。

~~`powershell -File scripts/activate_unity.ps1`~~ 单独 AppActivate 不能保证 AssetDatabase 刷新。
