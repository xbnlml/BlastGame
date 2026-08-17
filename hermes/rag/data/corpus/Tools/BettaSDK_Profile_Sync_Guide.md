# BettaSDK Profile 同步接入边界

> **AI 使用提示**：处理 Profile 同步、BettaSDK 接入或数据冲突时读取本文；先以本文边界和链路为准，SDK API 以源码为准。

## 适用范围

本文只说明 GameModule 如何接入 BettaSDK Profile 同步。SDK 内部 API 细节以当前 SDK 源码为准。

## 1. 数据链路

```text
GameModule data
  → UserModule / Profile model
  → BettaSDK ProfileHub
  → server profile
```

- GameModule 只通过 UserModule / Profile 层读写业务数据。
- BettaSDK 负责本地存档、版本和服务器同步。
- 业务模块不得直接修改 SDK 存档文件或绕过 ProfileHub。

## 2. 代码入口

| 问题 | 入口 |
|---|---|
| 玩家数据职责 | `Doc/MainGame/Player_Data_Logic.md` |
| UserModule 入口 | `UserModuleManager` / `UserMainData` |
| Profile 同步 | BettaSDK `ProfileHub` |
| 服务端请求 | BettaSDK `ServerHub` |
| 首登初始化 | UserModule 初始化流程 |
| 持久化字段 | 对应 `ProfileGame*Data` 类型 |

## 3. 接入规则

- 首登默认值由业务 Model 定义，不能散落在 UI。
- 增量修改先更新内存 Profile，再走统一持久化/同步入口。
- 同一业务字段只能有一个写入真源。
- 同步失败必须保留可重试状态，不能清除有效本地数据。
- Profile 版本或冲突处理由 SDK 同步层负责，业务层只提供数据和变更意图。

## 4. 排查顺序

1. 确认业务入口是否经过 UserModule。
2. 确认内存 Profile 是否正确更新。
3. 确认同步请求是否由 ProfileHub 发出。
4. 再检查版本、网络和服务端响应。

不要从 UI 或 SDK 底层日志开始反推业务职责。
