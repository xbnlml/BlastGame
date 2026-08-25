// Emit the official asset execution plan used by V3 Python request builder.
// Usage: node asset_execution_plan.mjs <asset-path> [<asset-path> ...]
import { repoModuleUrl, resolveRepo } from '../leveldb_sync/repo_paths.mjs';

const repo = resolveRepo();
const { readAssetSnapshot } = await import(repoModuleUrl(repo, 'Tools/level-editor/launcher/leveldb/assetSnapshot.mjs'));
const { computeDealConfigFingerprint } = await import(repoModuleUrl(repo, 'Tools/level-editor/launcher/leveldb/tierConfigMatch.mjs'));

const assets = process.argv.slice(2);
if (!assets.length) {
  console.error('usage: node asset_execution_plan.mjs <asset-path> [...]');
  process.exit(2);
}

const levels = [];
for (const assetPath of assets) {
  const snapshot = readAssetSnapshot(assetPath);
  if (!snapshot.ok) {
    console.error(JSON.stringify({ ok: false, assetPath, error: snapshot.error || 'asset parse failed' }));
    process.exit(3);
  }
  const match = /(?:^|[\\/])(\d+)\.asset$/i.exec(assetPath);
  if (!match) {
    console.error(JSON.stringify({ ok: false, assetPath, error: 'cannot infer level from asset filename' }));
    process.exit(4);
  }
  const boardFingerprint = snapshot.data.boardFingerprint;
  const tiers = (snapshot.data.tiers || []).map((raw, index) => {
    const config = normalizeConfig(raw);
    return {
      level: match[1],
      slot: `T${index + 1}`,
      tier: index + 1,
      board_fingerprint: boardFingerprint,
      deal_fingerprint: computeDealConfigFingerprint(config),
      config,
    };
  });
  if (tiers.length !== 5) {
    console.error(JSON.stringify({ ok: false, assetPath, error: `expected 5 tiers, got ${tiers.length}` }));
    process.exit(5);
  }
  levels.push({ level: match[1], assetPath, board_fingerprint: boardFingerprint, tiers });
}
console.log(JSON.stringify({ ok: true, levels }));

function normalizeConfig(config) {
  const ratios = Array.isArray(config.shuffleSplitRatios)
    ? config.shuffleSplitRatios.join(',')
    : String(config.shuffleSplitRatios || '');
  return {
    startDifficulty: Number(config.startDifficulty),
    shuffleSplitCount: Number(config.shuffleSplitCount),
    shuffleSplitRatios: ratios,
    shuffleOverflowFactor: String(config.shuffleOverflowFactor ?? 0),
  };
}
