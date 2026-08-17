import { loadRunStore, upsertRunEntry, saveRunStore } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/runStore.mjs';
import { computeDealConfigFingerprint } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/tierConfigMatch.mjs';
import { readAssetSnapshot } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/assetSnapshot.mjs';
const REPO = 'C:/Users/Administrator/Documents/BlastGame';
const store = loadRunStore(REPO, 'test');
const lv = '186';
const snap = readAssetSnapshot('C:/Users/Administrator/Documents/BlastGame/Assets/GameModule/GameMain/ConfigSo/Generated_enum/test/181_200/186.asset');
if (snap.ok) {
  const dealConfig = { startDifficulty: 19, shuffleSplitCount: 5, shuffleSplitRatios: '5,5,1,5,5', shuffleOverflowFactor: '0.5' };
  const dealFingerprint = computeDealConfigFingerprint(dealConfig);
  const entry = {
    fingerprintAlgorithm: 'sha256-v1', boardFingerprint: snap.data.boardFingerprint,
    dealFingerprint, fingerprint: dealFingerprint,
    identitySource: 'hermes-import', identityStatus: 'verified', dealConfig,
    matchedAssetSlots: [1], winRate: 0.50, failDistribution: null,
    sourceTierLabels: ['T2'],
    perResultMeta: { importedAt: '2026-08-17T00:00:00', sourceFileName: 'hermes-import-20260817.csv' },
    importedAt: '2026-08-17T00:00:00', sourceFileName: 'hermes-import-20260817.csv',
    sourceFormat: 'B', lastResolvedAt: null
  };
  upsertRunEntry(store, lv, entry, { mergeTierIndex: null });
  saveRunStore(REPO, store);
  const verify = loadRunStore(REPO, 'test');
  const t2 = verify.levels[lv].entries.filter(e => e.dealConfig?.startDifficulty == 19);
  console.log('验证 sd19 T2 entries:', t2.length, t2.map(e => e.winRate));
}
