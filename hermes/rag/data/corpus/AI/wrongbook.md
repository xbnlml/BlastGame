# Wrongbook

## WB-002：新增 `UtilsLog` 日志漏引入命名空间

- 错误：在 `GameMainSceneLoader.cs` 中新增 `UtilsLog.L(...)` 日志，但未引入 `BettaSDK`。
- 报错：`CS0103: The name 'UtilsLog' does not exist in the current context`。
- 原因：`UtilsLog` 不属于当前文件已有的 `Betta.Framework` 命名空间。
- 规则：新增日志调用前，确认日志类型所属命名空间；本项目使用 `UtilsLog` 时补充 `using BettaSDK;`。
- 修复：在 `GameMainSceneLoader.cs` 增加 `using BettaSDK;`，并通过编译验证。
