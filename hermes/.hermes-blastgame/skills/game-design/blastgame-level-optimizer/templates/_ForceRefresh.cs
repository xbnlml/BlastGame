using UnityEditor;
using System.IO;
using UnityEngine;

/// <summary>
/// 强制 Unity AssetDatabase.Refresh() — 放在 Assets/Editor/ 下，触发编译后自动运行。
/// 与 touch 现有 .cs + AppActivate 聚焦 Unity 一起使用。
/// .asset 文件修改后 Unity 的 AssetDatabase 缓存不会自动更新，
/// 这个脚本通过 domain reload → [InitializeOnLoadMethod] → AssetDatabase.Refresh()
/// 强制重新导入所有 asset。
/// 
/// 用法（由 Agent 自动执行，不手动操作）：
/// 1. patch asset
/// 2. 将此脚本写入 Assets/Editor/_ForceRefresh.cs
/// 3. touch 一个现有 .cs 文件（如 BlastWorkbenchWindow.Bot.cs）
/// 4. AppActivate 聚焦 Unity 窗口（关键！不聚焦编译不触发）
/// 5. 轮询 BuildLogs/_refresh_done.txt 确认完成
/// 6. 删除此脚本及 .meta
/// 7. 写 request.json
/// </summary>
public static class _ForceRefresh
{
    [InitializeOnLoadMethod]
    static void Refresh()
    {
        AssetDatabase.Refresh();
        var marker = Path.Combine(
            Directory.GetParent(Application.dataPath).FullName,
            "BuildLogs/_refresh_done.txt");
        File.WriteAllText(marker, "done");
    }
}
