import { loadRunStore, upsertRunEntry, saveRunStore } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/runStore.mjs';
import { computeDealConfigFingerprint } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/tierConfigMatch.mjs';
import { readAssetSnapshot } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/assetSnapshot.mjs';
const REPO = 'C:/Users/Administrator/Documents/BlastGame';
const store = loadRunStore(REPO, 'test');
const lv = '186';
const snap = readAssetSnapshot('C:/Users/Administrator/Documents/BlastGame/Assets/GameModule/GameMain/ConfigSo/Generated_enum/test/181_200/186.asset');
if (!snap.ok) { console.log('snap fail'); process.exit(1); }
const bfp = snap.data.boardFingerprint;
const tiers = [
  { sd: 0,  sc: 5, ratios: '10,10,0,0,0', of: '0.5',  wr: 0.63,  label: 'T1', slot: 0 },
  { sd: 19, sc: 5, ratios: '5,5,1,5,5',    of: '0.5',  wr: 0.50,  label: 'T2', slot: 1 },
  { sd: 23, sc: 5, ratios: '1,1,1,1,1',    of: '0.5',  wr: 0.3925,label: 'T3', slot: 2 },
  { sd: 30, sc: 5, ratios: '0,10,0,0,0',   of: '0.75', wr: 0.285, label: 'T4', slot: 3 },
  { sd: 40, sc: 5, ratios: '0,0,0,0,10',   of: '1',    wr: 0.185, label: 'T5', slot: 4 }
];
for (const t of tiers) {
  const dealConfig = { startDifficulty: t.sd, shuffleSplitCount: t.sc, shuffleSplitRatios: t.ratios, shuffleOverflowFactor: t.of };
  const dealFingerprint = computeDealConfigFingerprint(dealConfig);
  const entry = {
    fingerprintAlgorithm: 'sha256-v1', boardFingerprint: bfp, dealFingerprint, fingerprint: dealFingerprint,
    identitySource: 'hermes-import', identityStatus: 'verified', dealConfig,
    matchedAssetSlots: [t.slot], winRate: t.wr, failDistribution: null,
    sourceTierLabels: [t.label],
    perResultMeta: { importedAt: '2026-08-17T00:00:00', sourceFileName: 'hermes-import-20260817.csv' },
    importedAt: '2026-08-17T00:00:00', sourceFileName: 'hermes-import-20260817.csv',
    sourceFormat: 'B', lastResolvedAt: null
  };
  upsertRunEntry(store, lv, entry, { mergeTierIndex: null });
}
saveRunStore(REPO, store);
const verify = loadRunStore(REPO, 'test');
const es = verify.levels[lv].entries;
console.log('写入后 L186 entries:', es.length);
for (const e of es) {
  const dc = e.dealConfig;
  if (e.identitySource === 'hermes-import' && [0,19,23,30,40].includes(Number(dc.startDifficulty)))
    console.log('  ', e.sourceTierLabels, 'wr=', e.winRate, 'sd=', dc.startDifficulty);
}
