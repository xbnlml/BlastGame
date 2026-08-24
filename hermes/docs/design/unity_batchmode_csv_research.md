# Unity 批处理模式 CSV 写入失败 / 日志丢失 / 大规模批处理 — 外部研究笔记

调研日期：2026-08-14 ｜ 针对：Unity 6000.0.60f1 Windows 批处理模式（-batchmode -executeMethod -logFile -），
11 关 × 5 档 = 55 局对局，进程报 ok=55 成功但 CSV 未写出、tier 目录建了但空。

---

## Q1. File.WriteAllText 在批处理模式下写 CSV 失败的可能原因

**结论：批处理模式对 File.WriteAllText 本身无限制。** WriteAllText = 创建+写+关闭（同步完成，写后即落盘，
不存在缓冲丢失问题——缓冲问题只存在于 StreamWriter/FileStream 未 Flush/Dispose）。
来源：https://www.csharptutorial.net/csharp-file/csharp-write-text-files/ （微软文档同义）

真实原因排序（按本案相关度）：
1. **相对路径解析错位**：批处理下进程 cwd ≠ 脚本预期目录。案例：编辑器内调用能写 "Assets/test.txt"，
   命令行启动同一函数写不出来（SO 54758598）。→ CSV 用相对路径时文件写到"别处"而非被检查的目录。
   https://stackoverflow.com/questions/54758598/unity-command-line-executemethod-and-logfile-not-working
2. **异常被吞**：Directory.CreateDirectory 成功（说明权限/路径 OK、能建目录），File.WriteAllText 抛异常
   （磁盘满、PathTooLongException>260 字符、共享冲突/杀毒占用），被 try/catch 吞掉 → 目录在、文件无。
3. **权限**：CI/服务账户对目标盘（如 D:\ 根、Program Files）无写权限。
4. **文件被占用**：Windows Defender 实时扫描、CSV 被 Excel 打开 → IOException。
5. **路径过长**：tier/难度/关卡深层目录 + 长文件名超过 Windows 260 字符上限 → PathTooLongException。

## Q2. Debug.LogException 异常丢失 / 被吞的常见原因

官方文档两条关键原文（Unity 6000.3 EditorCommandLineArguments）：
- "In batch mode, Unity sends a **minimal version** of its log output to the console. However, the Log Files
  still contain the full log information."
- "-quit … can hide some error messages, but they still appear in the Editor's log file."
  来源：https://docs.unity3d.com/6000.3/Documentation/Manual/EditorCommandLineArguments.html

推论：
- 用 `-logFile -` 时 stdout 只有"最小版"日志，Debug.LogException 堆栈可能根本不出现在 stdout。
- **完整异常在 `%LOCALAPPDATA%\Unity\Editor\Editor.log`**（无论 -logFile 指向哪）。
- executeMethod 顶层抛异常时，Unity 会打印 "Aborting batchmode due to failure: executeMethod method X threw
  exception" 并以 **exit code 1** 退出（不是 0）。
  来源：https://discuss.gradle.org/t/unity-batchmode-build-fails-on-task-building-gradle-project/45438
- 本案 ok=55 成功 → 异常要么被方法内 try/catch 吞掉（且只 Debug.LogException，走了被过滤的 stdout），
  要么根本未执行到写文件处。

## Q3. -logFile - 输出到 stdout 的行为（是否可能丢日志）

- 官方：Windows 上 `-logFile -` 把日志导向 stdout，但 "Windows 应用默认没有 stdout 句柄，输出不会到控制台；
  只有以带有效 stdout 句柄的子进程启动（重定向句柄）才输出"。外部脚本能捕获 ⇒ 它是带句柄的子进程，正常。
- Unity 员工（Tautvydas-Zilys）确认：2016 年 "-logFile 无参数不生效"；2019.1 修复为"批处理模式默认输出到
  stdout，但仅在启动时带有有效 stdout 句柄时"。2019.1 之前/非子进程启动 → 什么也收不到。
  来源：https://discussions.unity.com/t/redirecting-standard-output-using-the-logfile-parameter-when-in-batchmode/622567
- **丢日志风险**：stdout 是管道，进程退出/崩溃时块缓冲可能未刷；外部脚本不落盘则进程一退即丢。
  且批处理只发"最小版"日志到 stdout（见 Q2），大量 Debug.Log 根本不进 stdout。
- 用户场景"日志被捕获但不落盘"符合预期：`-logFile -` 本就不产生日志文件；要落盘应指向具体文件路径，
  或自行订阅 Application.logMessageReceivedThreaded 写文件。完整日志始终在默认 Editor.log。
  来源：https://docs.unity3d.com/6000.3/Documentation/Manual/EditorCommandLineArguments.html、
  https://stackoverflow.com/questions/50093798/send-log-to-stdout-in-a-unity-app

## Q4. 大规模批处理内存/资源耗尽导致写文件失败

- 真实案例：批处理/无渲染下存在内存泄漏——SkinnedMeshRenderer 活跃时 ~4KB/秒级持续泄漏，禁用 renderer
  后停止（多用户验证）。长跑 55 局后内存耗尽 → GC/写入异常。
  来源：https://discussions.unity.com/t/batchmode-memory-leak-and-fix/482236
- Issue Tracker：批处理模式渲染时桌面平台有巨大内存泄漏，新版泄漏更快（约 1GB/5 秒）。
  https://issuetracker.unity3d.com/issues/unity-runtime-has-huge-memory-leak-while-rendering-in-batchmode-on-desktop-platforms
- 资源耗尽两种后果：
  a. OOM/崩溃 → 退出码非 0（本案未出现）。
  b. **文件句柄泄漏**：循环里 StreamWriter/FileStream 不 Dispose → 55 局后句柄耗尽 → 后面的写入抛
     IOException（若被吞则"目录建了文件没有"）。
- Unity 6 批处理 + -quit：默认等待异步任务完成，超时 300 秒（-quitTimeout 可调）；异步代码 + -quit 可能
  hang。Unity 6000 可用 `-log-memory-performance-stats` 观测内存。
  来源：https://docs.unity3d.com/6000.3/Documentation/Manual/EditorCommandLineArguments.html、
  https://dev.to/attiliohimeki/investigating-memory-issues-in-unity-55am

## Q5. 同类 case：批处理跑 N 次后"成功但文件没写"的排查经验

- **几乎同症状案例**："Jenkins: Unity batch mode build successful - Build folder empty"——退出码 0、
  "Exiting batchmode successfully"、日志无异常，但产物目录为空。
  来源：https://stackoverflow.com/questions/54025018/jenkins-unity-batch-mode-build-successful-build-folder-empty
- **方法根本没执行 / 没走到写文件**："executeMethod 和 logFile 不工作"——编辑器内正常、命令行不写文件，
  且方法名写错也不报错。教训：先在 executeMethod 首行写文件/打标记，确认方法真的被调用。
  来源：https://stackoverflow.com/questions/54758598/
- **异步/后台线程是最大嫌疑**（本案 BatchRunner 刚大改）：Unity 员工 Bunny83 明确——
  "Unity 不管理你的后台线程；executeMethod 返回即退出，后台任务没跑完会被杀"。
  若代码改为 async/await 或 Task.Run 且未同步等待（GetAwaiter().GetResult()/Join），则：ok=55 同步打印，
  CSV 写入落在未完成的异步 continuation → 进程退出 → 文件全空/缺失，退出码仍 0。
  来源：https://discussions.unity.com/t/how-to-execute-async-method-in-batchmode-correctly-questions-about-how-to-execute-async-method-in-batchmode/225878
- 排查 checklist（对本案）：
  1. 查 `%LOCALAPPDATA%\Unity\Editor\Editor.log`——完整日志，含被 -quit / -logFile - 隐藏的异常与
     "Aborting batchmode" 字样。
  2. 确认 executeMethod 入口确实执行（首行写标记文件）。
  3. 检查是否引入 async/后台线程且未同步等待。
  4. CSV 用绝对路径（相对路径在批处理下 cwd 不可靠）。
  5. 每局写入 try/catch 吞异常？StreamWriter 是否 finally 里 Dispose/Flush？
  6. 小规模正常→大规模失败：优先查内存泄漏、文件句柄泄漏、磁盘满、路径 >260 字符。

## 关键来源 URL 汇总
- https://docs.unity3d.com/6000.3/Documentation/Manual/EditorCommandLineArguments.html （-quit 隐藏错误、minimal log、-logFile -、300s async 超时、编译错误 exit 1）
- https://discussions.unity.com/t/redirecting-standard-output-using-the-logfile-parameter-when-in-batchmode/622567 （-logFile - 行为、stdout 句柄、2019.1 修复）
- https://stackoverflow.com/questions/54758598/unity-command-line-executemethod-and-logfile-not-working （编辑器能写、命令行不写）
- https://stackoverflow.com/questions/54025018/jenkins-unity-batch-mode-build-successful-build-folder-empty （成功但产物空）
- https://discussions.unity.com/t/batchmode-memory-leak-and-fix/482236 （批处理内存泄漏）
- https://discussions.unity.com/t/how-to-execute-async-method-in-batchmode-correctly-questions-about-how-to-execute-async-method-in-batchmode/225878 （后台线程/异步不被管理）
- https://issuetracker.unity3d.com/issues/unity-runtime-has-huge-memory-leak-while-rendering-in-batchmode-on-desktop-platforms
- https://discuss.gradle.org/t/unity-batchmode-build-fails-on-task-building-gradle-project/45438 （Aborting batchmode…threw exception, exit 1）
- https://stackoverflow.com/questions/50093798/send-log-to-stdout-in-a-unity-app
