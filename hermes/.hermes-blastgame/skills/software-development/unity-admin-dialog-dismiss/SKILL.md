---
name: unity-admin-dialog-dismiss
description: "Launch Unity Editor on Windows with automatic dismissal of the 'Unity is running as administrator' dialog. Full workflow: kill old process → start watchdog → launch Unity → verify."
version: 2.0.0
author: Hermes Agent
platforms: [windows]
---

# Unity 管理员弹窗自动关闭 + 启动流程

## 完整命令

```powershell
# Step 1: Kill existing Unity
taskkill //F //IM Unity.exe

# Step 2: Start watchdog script that auto-clicks the admin dialog
# (see scripts/watchdog.ps1 below)

# Step 3: Launch Unity
"C:/Program Files/Unity/Hub/Editor/6000.0.60f1/Editor/Unity.exe" -projectPath "C:/Users/Administrator/Documents/BlastGame" -logFile "BuildLogs/unity-launch.log"

# Step 4: Verify (memory > 500MB = loaded)
```

## 脚本：watchdog.ps1

路径：`Doc/AI/multi-tier-designer/scripts/watchdog.ps1`

```powershell
$ErrorActionPreference = "Stop"
$targetTitle = "Unity is running as administrator."
$ws = New-Object -ComObject WScript.Shell

for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    if ($ws.AppActivate($targetTitle)) {
        Start-Sleep -Milliseconds 500
        $ws.SendKeys("{ENTER}")
        exit 0
    }
}
```

## 调用方式（agent 执行时）

```bash
# 1. 杀掉旧 Unity
taskkill //F //IM Unity.exe

# 2. 启动 watchdog（background）
terminal(background=true, command='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "Doc/AI/multi-tier-designer/scripts/watchdog.ps1"')

# 3. 启动 Unity（background）
terminal(background=true, command='"...Unity.exe" -projectPath "..." -logFile "BuildLogs/unity-launch.log"')

# 4. 等 60s 后验证
terminal(command='sleep 60 && tasklist | grep Unity.exe')
```

## 弹窗未点掉的备选方案

如果 `SendKeys` 失败（从后台进程发不出），用 UIAutomation 直接找按钮控件并发送 BM_CLICK：

```powershell
Add-Type -AssemblyName UIAutomationClient
$unity = Get-Process Unity -ErrorAction SilentlyContinue
$element = [System.Windows.Automation.AutomationElement]::FromHandle($unity.MainWindowHandle)
$all = $element.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {
    if ($e.Current.Name -eq "I wish to continue at my own risk") {
        $rect = $e.Current.BoundingRectangle
        $cx = [int]($rect.X + $rect.Width / 2)
        $cy = [int]($rect.Y + $rect.Height / 2)
        # Use SetCursorPos + mouse_event (需 SetForegroundWindow 前置)
        break
    }
}
```

## 诊断方法

如果弹窗没被点掉，先用这个脚本检查弹窗的实际结构：

```powershell
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "Doc/AI/multi-tier-designer/scripts/find_dialog.ps1"
```

（已提供在 `scripts/find_dialog.ps1`，使用 EnumWindows + UIAutomation 枚举子控件）

## 常见失败原因

| 现象 | 原因 | 解决 |
|------|------|------|
| `FindWindow` 找不到对话框 | 后台进程的 UIPI 限制 | 改用 `EnumWindows` + `GetWindowText` 逐个枚举 |
| `SendKeys`/`BM_CLICK` 无效 | 按钮是 `Pane` 控件不是 `Button` | 只能鼠标模拟点击，不能用窗口消息 |
| `mouse_event` 点了没反应 | 窗口未前台或前台锁 | 先用 `SwitchToThisWindow` 再 `SetForegroundWindow` |
| `InvokePattern` 不可用 | 自定义绘制控件不暴露自动化模式 | 只能用坐标点击 (BoundingRectangle) |

## 核心原理

Unity 6 的管理员弹窗是 Unity 自绘的 IMGUI 窗口，不是标准 Windows 对话框：
- 窗口类名未知（并非 `#32770`）
- 按钮控件类型为 `Pane`（不是 `Button`）
- 子控件不暴露 `InvokePattern` 等自动化模式
- 唯一可靠的交互方式：找到控件的 `BoundingRectangle` → 鼠标模拟点击其中心坐标

## 可靠方法（EnumWindows + UIA + mouse_event）

```powershell
Add-Type -AssemblyName UIAutomationClient
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class W {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc e, IntPtr p);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder t, int m);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SwitchToThisWindow(IntPtr h, bool a);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    public delegate bool EnumWindowsProc(IntPtr h, IntPtr p);
}
"@
# EnumWindows to find dialog (NOT FindWindow - fails from background)
$foundHwnd = [IntPtr]::Zero
[W]::EnumWindows({ param($h, $p)
    $sb = New-Object System.Text.StringBuilder 256
    $len = [W]::GetWindowText($h, $sb, 256)
    if ($len -gt 0 -and [W]::IsWindowVisible($h) -and $sb.ToString() -eq "Unity is running as administrator.") {
        $script:foundHwnd = $h; return $false
    }; return $true
}, [IntPtr]::Zero) | Out-Null

[W]::SwitchToThisWindow($foundHwnd, $true)
[W]::SetForegroundWindow($foundHwnd) | Out-Null

# UIA to find Pane "I wish to continue at my own risk", get rect, mouse click
$element = [System.Windows.Automation.AutomationElement]::FromHandle($foundHwnd)
$all = $element.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {
    if ($e.Current.Name -eq "I wish to continue at my own risk") {
        $rect = $e.Current.BoundingRectangle
        $cx = [int]($rect.X + $rect.Width / 2)
        $cy = [int]($rect.Y + $rect.Height / 2)
        [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($cx, $cy)
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        # Fallback: mouse_event
        Add-Type @"
[DllImport("user32.dll")] public static extern void mouse_event(int f,int x,int y,int d,int e);
"@ -Name M
        [M]::mouse_event(0x0002,0,0,0,0); Start-Sleep 50; [M]::mouse_event(0x0004,0,0,0,0)
    }
}
```

## watchdog.ps1

完整路径：`Doc/AI/multi-tier-designer/scripts/watchdog.ps1`

- 每 1 秒轮询一次
- 使用 `EnumWindows` 而非 `FindWindow`
- 发现弹窗后：`SwitchToThisWindow` → `SetForegroundWindow` → UIA 获取按钮坐标 → `mouse_event` 点击
- 90 秒超时
- 必须带 `-STA` 参数运行（UIAutomation 需要 STA 线程）

## 注意事项

- PowerShell 默认 MTA，UIAutomation 需要 STA → 启动时加 `-STA`
- `FindWindow($null, $title)` 从后台进程可能找不到窗口 → 用 `EnumWindows` + `GetWindowText` 遍历
- 同步启动 watchdog 和 Unity 时，先启动 watchdog 再启动 Unity
- 使用 `terminal(background=true)` 分别启动两个进程
- **从 `terminal(background=true)` 启动的 PowerShell 无法可靠点击弹窗**——背景进程受 Windows UIPI 限制，`SendKeys`、`mouse_event`、`SendInput` 均可能被拦截。如需可靠方案，建议：
  1. 用 `execute_code` 中的 `subprocess` 启动（非后台，前台运行）
  2. 查找 `AllowSetForegroundWindow` API 授权
  3. 或使用 Windows 计划任务 / 常驻 COM 组件
