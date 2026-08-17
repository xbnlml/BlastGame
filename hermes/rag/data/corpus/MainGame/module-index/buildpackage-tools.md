# buildpackage 外部构建链路导航

- 范围：非 `Assets/GameModule` 目录内模块，保留原索引中的打包链路信息。

## buildpackage（移动端打包链路：iOS / Android）

### 总体定位

- 目录：`Tools/Python/buildpackage/`
- 角色：Jenkins 打包辅助链路，聚焦 iOS/Android 包产物与通知，不涉及游戏逻辑。
- 约束口径：你后续提到“打包流程”时，默认指向这里的 skill 与脚本流。
- `JenkinsAppVersionPrebuild`：只读 `-BlastJenkins*` 命令行；Jenkins 经 `JenkinsAppVersionFile.sh` 转参后 `-executeMethod ...ApplyFromJenkins` 写回工程文件。Android keystore 密码由同文件 `JenkinsAndroidKeystorePreprocessBuild`（`IPreprocessBuildWithReport`）在 `BuildPlayer` 同进程从 `BettaSDKConfig` 注入（Debug/Release 均走，因密码不落盘、且 BettaSDK Automation 仅 Release 注入）。同时把 `BettaSDKConfig.AndroidKeyStorePath`（工程相对路径）解析为绝对路径写回 `FacebookSettings.androidKeystorePath`。
- `JenkinsAppVersionFile.sh`：`blast_sync_jenkins_app_version_file` / `blast_check_s3_version_conflict`（Android/iOS 整包 S3 版本预检共用）。
  - Jenkins 参数职责：`BUILD_ENV` 控制签名/分发；`IS_UNITY_DEVELOP` 控制 Unity Debug/Release 构建（未传兼容旧行为）；`OPEN_GM` 仅覆盖 `MODULE_GM`。`OnlyHotfix=true` 时 iOS 不上传 TestFlight。
- Android：`ANDROID_BUILD_APP_BUNDLE` → `-BlastJenkinsAndroidAppBundle` → `BettaSDKConfig.asset`。
- 整包资源构建前：Android/iOS 调用 `BlastGame.Editor.LocaleFontCharacterBuilder.BuildForBuild` 生成多语言字体字符集；`OnlyHotfix`、`OnlyPostBuild`、iOS `OnlyXcode` 跳过。

### 脚本职责索引

- `JenkinsProcess.py`
  - 角色：将 Jenkins 构建号写回 `ClientInfo.json`（`ClientBuild` 字段）。
  - 关键方法：`WriteJenkinBuildNumber`。
  - 运行时联动：`GameMain.Run` 会把 `ClientBuild` 写入 `PlayerPrefs("ClientBuild")`；`UILoading` 启动先展示本地资源值，热更完成后会再次读取并刷新显示。

- `JenkinsNotifyDingTalk.py`
  - 角色：汇总 Jenkins 构建信息并发送钉钉通知（支持下载链接与构建变更摘要）。
  - 核心类：`NotifyHelper`
  - 关键方法：
    - Jenkins 信息读取：`getLastBuildInfo`、`getBuildBranchName`、`getBuildParameter`
    - 版本信息读取：`getVersionInfo`（按平台读取 Android/iPhone build number）
    - 通知发送：`dingTalkSendNotify`、`sendNotification`

- `JenkinsNotifyFail.sh`
  - 角色：`trap ERR` 失败回调；仅当 `BLAST_JENKINS_FAIL_DINGTALK_NOTIFY=true` 时推送失败钉钉（默认不推送）。

- `JenkinsRecorder.py`
  - 角色：记录/读取上次构建信息（sha + branch）到临时文件，供后续通知或比对使用。
  - 关键方法：`getLastBuildInfo`、`saveBuildInfo`。

- `JenkinsUtils.py`
  - 角色：通用工具层（命令执行、路径/文件、Jenkins URL、Unity 资产字段读取等）。
  - 关键方法：
    - 路径与文件：`getProjectDir`、`readFileContent`、`writeFileContent`
    - Jenkins URL：`getJenkinsHomePage`、`getJenkinsProjectUrl`
    - 版本字段解析：`readUnityAssetField`

- `JenkinsMacWorkspacePreflight.sh`
  - 角色：macOS Bee IPC（UDS 路径长度）预检。

- `JenkinsCleanLocalBuildArtifacts.sh`
  - 角色：打包前按模式清理上次构建残留（热更仅资源/DLL；整包含 `dist` 与平台 `build`；`OnlyXcode` 跳过）；不清理 `Library`。
  - 关键方法：`blast_jenkins_clean_local_build_artifacts`。

- `JenkinsPostBuildCommon.sh`
  - 角色：Android/iOS PostBuild 公共归档逻辑（版本解析、产物查找、downloads/8081、钉钉字段）。
  - 口径：归档后缀跟随源产物（Android `.apk`/`.aab`，iOS `.ipa`）；同时存在时优先 `.aab`。
  - Store：`.aab` / iOS Release 跳过扫码安装分发；AAB 钉钉 `ReleasePlayConsole`（手动传 Play + `BLAST_STORE_PACKAGE_PATH`）。

- `JenkinsUploadTestFlight.sh`
  - 角色：iOS Release 可选上传 App Store Connect；`SUCCESS`/`SKIPPED` 均发钉钉，`FAILED` 不在此脚本发。

- `JenkinsSubmoduleSync.sh`
  - 角色：打包前同步 `Packages/BettaSDK`、`Packages/BettaFramework`、`Packages/BettaInterface`；有 `KEYCHAIN_PASSWORD` 时先解锁 login keychain（避免 HTTPS/`osxkeychain` 卡住），再 `git-lfs` 检查 + 按 `.gitmodules` tracking branch fetch。
  - 关键方法：`blast_jenkins_sync_submodules`、`blast_jenkins_unlock_login_keychain`（由 `JenkinsUnityPrep.sh` 在 `git reset --hard` 之后调用）。

- `GenerateQRCode.py`
  - 角色：为下载链接生成二维码（用于包分发）。
  - 关键方法：`generate_qr_code`、`main`。

- `SimpleHTTPServer.py`
  - 角色：本地/局域网临时文件分发服务器，自动列出 `.apk/.aab/.ipa` 文件下载页。
  - 核心类：`FileHandler`
  - 关键方法：`do_GET`、`get_local_ip`。

## jenkins-batch（Lv-Config / Bot 批跑）

- 目录：`Tools/Python/jenkins-batch/`
- 钉钉链接：优先 `${BUILD_URL}artifact/BuildArtifacts/...`（`jenkins_log_url.sh`）；Job 须 Archive `BuildArtifacts/**`。细则见 `Tools/Python/buildpackage/JenkinsBuildFlow_README.md` §8.3。
