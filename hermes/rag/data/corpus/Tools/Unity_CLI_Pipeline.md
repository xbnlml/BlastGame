# Unity CLI（Pipeline）

> **AI 使用提示**：需要查询或操作正在运行的 Unity Editor、Console、场景、Prefab、测试或截图时优先使用本文；命令入口为 `unity command <command>`，破坏性操作先确认参数。

本项目使用 Unity 官方 Unity CLI beta，通过 `com.unity.pipeline` 控制正在运行的 Unity Editor。它不是 UGS CLI，也不是 MCP。

## 当前版本

- Unity CLI：`1.0.0-beta.3`
- Pipeline 包：`com.unity.pipeline 0.4.0-exp.1`
- 项目要求：Unity 6.0+

## 安装与验证

macOS/Linux：

```bash
curl -fsSL https://public-cdn.cloud.unity3d.com/hub/prod/cli/install.sh \
  | UNITY_CLI_CHANNEL=beta bash
source ~/.unity/env
unity --version
```

在项目目录、且 Unity Editor 已打开时：

```bash
unity auth login
unity pipeline install
unity pipeline list
```

确认列表中出现 `Pipeline: Installed`，然后用下面命令查看当前 CLI 支持的命令：

```bash
unity command
unity command <command-name> --help
```

## 项目使用约定

执行前确保当前目录为项目根目录，Unity Editor 已打开并完成编译。CLI 连接的是本机运行中的 Editor，服务只绑定本机地址并使用短期 token。

## 常规操作命令

命令格式是 `unity command <Pipeline 命令> [参数]`。参数必须以当前版本的命令帮助为准：

```bash
unity command
unity command <name> --help
```

按日常使用频率，优先记这些命令：

| 场景 | 命令名 |
|---|---|
| 编辑器状态 | `editor_status`、`editor_focus` |
| 播放控制 | `editor_play`、`editor_pause`、`editor_stop` |
| 日志与截图 | `get_console_logs`、`clear_console`、`capture_game_view`、`capture_scene_view` |
| 场景 | `create_scene`、`open_scene`、`save_scene`、`save_all`、`get_scene_hierarchy` |
| GameObject | `create_gameobject`、`find_gameobjects`、`set_transform`、`set_active`、`set_parent` |
| 组件 | `add_component`、`remove_component`、`get_component_properties`、`set_component_properties` |
| 资源 | `find_assets`、`create_asset`、`import_asset`、`move_asset`、`write_text_file` |
| Prefab | `create_prefab`、`instantiate_prefab`、`apply_prefab_overrides` |
| 脚本 | `create_script`、`attach_script`、`set_serialized_field` |
| 编译与测试 | `recompile`、`list_tests`、`run_tests`、`test_status` |
| 构建 | `build`、`build_status`、`list_build_targets`、`get_build_settings` |
| 包管理 | `package_list`、`package_add`、`package_remove`、`package_resolve` |
| 烘焙 | `bake_lighting`、`bake_navmesh`、`lighting_bake_status` |
| 运行时 | `runtime_status`、`set_timescale`、`simulate_key`、`simulate_pointer` |

典型调用方式：

```bash
unity command editor_status
unity command find_gameobjects --help
unity command get_console_logs
unity command capture_game_view
unity command recompile
unity command run_tests --help
```

资源、场景和 GameObject 的修改命令会改变项目文件或 Editor 状态；删除、构建、烘焙和运行时 `eval` 前必须先确认目标和参数。

## 连接故障排查

如果 `unity command` 报 `No Unity Editor instances found with reachable Pipeline servers`：

1. 确认 Unity Editor 已打开本项目。
2. 安装包后重启一次 Editor，让 Pipeline server 完成初始化。
3. 执行 `unity pipeline list`，确认 `Pipeline=true` 且 `服务器可达=true`。
4. 若项目正在编译，等待编译结束后再执行命令。

不要把 `unity command` 当作传统 `Unity -batchmode -executeMethod` 的替代品；前者操作运行中的 Editor，后者仍适合无界面的 CI 构建。

当前版本的完整分类还包括：动画、材质、导航、项目设置、编辑器生命周期、热重载和运行时命令。具体参数以当前安装版本的帮助输出为准；实验版命令可能变化。

## 官方资料

- [Unity CLI](https://docs.unity.com/en-us/unity-cli)
- [com.unity.pipeline 文档](https://docs.unity3d.com/Packages/com.unity.pipeline@latest)
- [Unity CLI 安装器](https://public-cdn.cloud.unity3d.com/hub/prod/cli/install.sh)
