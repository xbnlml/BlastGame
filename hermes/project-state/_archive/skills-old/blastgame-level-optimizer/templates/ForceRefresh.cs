// _ForceRefresh.cs — AssetDatabase.Refresh() 强制刷新模板
// 用法：复制到 Assets/Editor/，touch 现有 .cs，AppActivate 聚焦 Unity
// ⚠️ 只能引用 UnityEngine, UnityEditor, System.IO 等标准程序集
// ⚠️ 禁止引用 LevelProfileConfig 等游戏类型（编译报错 CS0246）
// ⚠️ 每次用唯一类名（_F{timestamp}{random}），避免重复跳过编译
// ⚠️ Bot 运行时 Unity 主线程忙，文件监控不处理，等空闲再写

using UnityEditor;
using System.IO;
using UnityEngine;

public static class _ForceRefresh
{
    [InitializeOnLoadMethod]
    static void Refresh()
    {
        var marker = Path.Combine(
            Directory.GetParent(Application.dataPath).FullName,
            "BuildLogs/_refresh_done.txt");
        if (File.Exists(marker)) return;
        AssetDatabase.Refresh();
        File.WriteAllText(marker, "ok");
    }
}
