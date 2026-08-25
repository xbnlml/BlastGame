// 计算指定关卡的 asset boardFingerprint（用官方 leveldb 模块，与 write_level_db 一致）
// 用法: node get_asset_board_fp.mjs <asset路径>
// 依赖: 可选环境变量 BLASTGAME_REPO；未设置时按 checkout/当前用户 Documents 发现 Unity 工程
import { repoModuleUrl, resolveRepo } from './repo_paths.mjs';

const repo = resolveRepo();
const { readAssetSnapshot } = await import(repoModuleUrl(repo, 'Tools/level-editor/launcher/leveldb/assetSnapshot.mjs'));

const assetPath = process.argv[2];
if (!assetPath) {
  console.error('用法: node get_asset_board_fp.mjs <asset路径>');
  process.exit(1);
}
const snap = readAssetSnapshot(assetPath);
if (!snap.ok) {
  console.error(JSON.stringify({ ok: false, error: snap.error }));
  process.exit(1);
}
console.log(JSON.stringify({ ok: true, boardFingerprint: snap.data.boardFingerprint }));