// 计算指定关卡的 asset boardFingerprint（用官方 leveldb 模块，与 write_level_db 一致）
// 用法: node get_asset_board_fp.mjs <asset路径>
import { readAssetSnapshot } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/assetSnapshot.mjs';

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