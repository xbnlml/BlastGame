# Buildpackage Mobile Orchestrator（移动端打包）

本文对应 `Playbooks/buildpackage-mobile-orchestrator.md`，用于承载 iOS / Android 打包链路文档（独立于 `Doc/AI`）。

## 1. 范围

- Jenkins 构建号写入与版本读取校验
- 构建通知（如钉钉）
- 包产物二维码与局域网分发
- iOS / Android 出包流程编排
- iOS Release 可选 TestFlight 上传（2026-05-21，见专题文档）

Android：Jenkins `ANDROID_BUILD_APP_BUNDLE` → shell 转 `-BlastJenkinsAndroidAppBundle` → `ApplyFromJenkins` 写 `BettaSDKConfig.asset`（与版本参数同一路径：只读命令行，有参才改）。

## 2. 路由关系

- 玩法逻辑文档在 `Doc/MainGame/`，不与打包流程混放。
- 当需求关键词为“打包流程 / 移动端打包 / Jenkins 打包 / Android/iOS 出包 / 构建通知”时，优先归档到本模块。

## 3. 关联文档

- Playbook：`Playbooks/buildpackage-mobile-orchestrator.md`
- 主游戏导航：`Doc/MainGame/Blast_MainGame.md`
- iOS TestFlight 开关：见 `JenkinsUploadTestFlight.sh` 与本页 §4 类功能定位。
- 打包流程详述：`Tools/Python/buildpackage/JenkinsBuildFlow_README.md`

## 5. 热更 BUILD_ID / git tag / S3 备份命名

**真源脚本**：`Tools/Shell/utils.sh`

| 函数 | 用途 |
|------|------|
| `get_version` | 读 `ProjectSettings.bundleVersion`（S3 预检仅在无 Jenkins `APP_VERSION` 等时由 `blast_check_s3_version_conflict` 回退） |
| `get_platform_version_code` | Android `versionCode` / iOS `buildNumber.iPhone` |
| `compose_build_id` | 生成完整 BUILD_ID |
| `compose_git_tag_name` | 生成 git tag |
| `compose_s3_versions_backup_name` | `versions_{BUILD_ID}.json` |
| `compose_s3_manifest_backup_name` | `{Platform}_manifest_{BUILD_ID}` |

`BUILD_ID` 格式：`{bundleVersion}_{versionCode}_{resourceVersion}_{YYYYMMDD_HHMM}_{gitShort}`

- S3 / git tag / 回滚均消费同一 `BUILD_ID`，不在各脚本重复拼装。
- 回滚：`Tools/Shell/RollbackHotfix.sh <platform> <bundleVersion> <BUILD_ID>`

详见 `JenkinsBuildFlow_README.md` §3.7–3.8。

## 4. 类功能定位

| 类/文件 | 功能 | 路径 |
|---|---|---|
| `JenkinsAppVersionPrebuild` | Jenkins `-executeMethod ApplyFromJenkins`：打包前写回 ProjectSettings / BettaSDKConfig（版本、versionCode、AAB）；同文件 `JenkinsAndroidKeystorePreprocessBuild` 在 Android `BuildPlayer` 前从 `BettaSDKConfig` 注入 keystore（含 Debug，密码不落盘）；并把相对 keystore 路径解析为绝对路径写回 `FacebookSettings.androidKeystorePath` | `Assets/GameModule/Editor/JenkinsAppVersionPrebuild.cs` |
| `JenkinsBuildBridge` | iOS 只同步 Google Sign-In，Android 额外同步 GPGS，再调 `BettaSDK.Editor.Automation` 对应入口 | `Assets/BuildApp/Editor/JenkinsBuildBridge.cs` |
| `JenkinsProcess.py` | 打包流程主编排脚本 | `Tools/Python/buildpackage/JenkinsProcess.py` |
| `JenkinsNotifyDingTalk.py` | 构建通知发送（钉钉） | `Tools/Python/buildpackage/JenkinsNotifyDingTalk.py` |
| `GenerateQRCode.py` | 产物二维码生成 | `Tools/Python/buildpackage/GenerateQRCode.py` |
| `SimpleHTTPServer.py` | 局域网分发 HTTP 服务 | `Tools/Python/buildpackage/SimpleHTTPServer.py` |
| `BlastNasFtpPurgeSystem.sh` | Jenkins 一键删除 FTP `blast/system` | `Tools/Python/buildpackage/BlastNasFtpPurgeSystem.sh` |
| `BlastS3PurgeBundleVersion.sh` | Jenkins 一键删除 S3 `blast/<平台>/<版本>/` | `Tools/Python/buildpackage/BlastS3PurgeBundleVersion.sh` |
| `JenkinsUploadTestFlight.sh` | iOS Release 可选上传 TestFlight（非阻断） | `Tools/Python/buildpackage/JenkinsUploadTestFlight.sh` |

维护规则：打包链路新增入口脚本或编辑器类时，补充到本表并同步主导航。
