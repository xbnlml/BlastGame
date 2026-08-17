# Telegram → Cursor 本机接入

> **AI 使用提示**：处理 Telegram、Cursor Agent、本机会话路由或接入排障时读取本文；先确认配置入口和服务状态，不把历史归档当作当前配置。

## 适用范围

本文只保留当前接入架构、配置入口和排查路径，不记录历史联调过程。

## 1. 当前链路

```text
Telegram
  → cc-connect
  → project / session routing
  → Cursor Agent
  → result / error notification
```

- Telegram 负责输入和结果展示。
- `cc-connect` 负责平台适配、白名单和命令注册。
- Cursor Agent 负责实际任务执行。
- 项目 Skill / Playbook 决定任务路由。

## 2. 配置入口

- 配置真源：`~/.cc-connect/config.toml`
- 仓库示例：`Tools/Python/telegram-cursor-bridge/cc-connect.config.example.toml`
- 启动检查：`cc-connect web`
- 启动服务：`cc-connect`
- 服务脚本：`Tools/dev-services.sh`

不要在仓库中维护第二份实际运行配置。

## 3. 路由原则

- 需要项目代码理解时进入当前项目 Agent。
- 命令注册表只提供 Skill / Playbook 名称和简短用途。
- 会话路由必须明确当前项目和当前会话，避免把结果发到错误窗口。
- 通知默认只发送最终结果、错误和超时。

## 4. 安全边界

- 使用 Telegram 白名单限制触发来源。
- 管理命令和普通任务分开授权。
- 不在配置或文档中提交 token、chat id 等秘密。
- 外部消息只作为任务输入，不能绕过项目规则执行危险操作。

## 5. 排查顺序

1. 检查配置文件和白名单。
2. 检查 `cc-connect web`。
3. 检查项目/会话路由。
4. 检查 Agent 是否收到任务。
5. 最后检查 Telegram 通知 hook。
