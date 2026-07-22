# BlastGame Hermes Profile — 迁移指南

## 迁移到其他机器

拷贝整个 `D:\download\Hermes` 文件夹到目标机器上任意位置。

需要在目标机器上**重建一次目录链接**，让 Hermes 找到 blastgame profile：

```powershell
# PowerShell
New-Item -ItemType Junction -Path "$env:LOCALAPPDATA\hermes\profiles\blastgame" -Target "D:\path\to\Hermes\.hermes-blastgame"
```

> 把上面路径换成实际位置即可

## 使用方式

### 桌面端
1. 启动 Hermes Desktop
2. 左上角或状态栏切换 profile 为 **blastgame**
3. 此时 memory/skill/session 全是 BlastGame 专属
4. 切回 **default** 恢复通用工作

### 终端
```bash
hermes -p blastgame
# 或
blastgame chat
```

## 结构说明

```
D:\download\Hermes/
├── .hermes-blastgame/       ← BlastGame Hermes 完整家目录
│   ├── config.yaml          ← 独立配置
│   ├── skills/game-design/  ← 7 个 BlastGame skill
│   ├── memories/            ← BlastGame 专属记忆
│   └── sessions/            ← 会话历史
├── tools/                   ← Python 工具脚本
├── preflight.py             ← 已有
└── ...
```

## 注意事项
- Junction 建一次就行了，后续拷文件夹不用重建——除非路径变了
- default profile 的 memory 已清理 BlastGame 内容，互不干扰
- 两个 profile 的 model config 独立，可以各自配不同模型
