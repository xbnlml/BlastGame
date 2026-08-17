import fs from 'node:fs';
import path from 'node:path';
import { loadRunStore, upsertRunEntry, saveRunStore } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/runStore.mjs';
import { computeDealConfigFingerprint } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/tierConfigMatch.mjs';
import { readAssetSnapshot } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/assetSnapshot.mjs';

const REPO = 'C:/Users/Administrator/Documents/BlastGame';
const store = loadRunStore(REPO, 'test');
const lv = '186';
const snap = readAssetSnapshot('C:/Users/Administrator/Documents/BlastGame/Assets/GameModule/GameMain/ConfigSo/Generated_enum/test/181_200/186.asset');
console.log('asset 快照 ok:', snap.ok);
if (snap.ok) {
  const boardFingerprint = snap.data.boardFingerprint;
  const dealConfig = { startDifficulty: 0, shuffleSplitCount: 5, shuffleSplitRatios: '10,10,0,0,0', shuffleOverflowFactor: '0.5' };
  const dealFingerprint = computeDealConfigFingerprint(dealConfig);
  const entry = {
    fingerprintAlgorithm: 'sha256-v1',
    boardFingerprint,
    dealFingerprint,
    fingerprint: dealFingerprint,
    identitySource: 'hermes-import',
    identityStatus: 'verified',
    dealConfig,
    matchedAssetSlots: [0],
    winRate: 0.63,
    failDistribution: null,
    sourceTierLabels: ['T1'],
    perResultMeta: { importedAt: '2026-08-17T00:00:00', sourceFileName: 'hermes-import-20260817.csv' },
    importedAt: '2026-08-17T00:00:00',
    sourceFileName: 'hermes-import-20260817.csv',
    sourceFormat: 'B',
    lastResolvedAt: null
  };
  upsertRunEntry(store, lv, entry, { mergeTierIndex: null });
  saveRunStore(REPO, store);
  console.log('已补写 L186 T1: wr=0.63 sd=0');
  // 验证
  const verify = loadRunStore(REPO, 'test');
  const entries = verify.levels[lv].entries;
  const t1 = entries.filter(e => e.dealConfig?.startDifficulty == 0);
  console.log('验证 sd0 T1 entries:', t1.length);
  for (const e of t1) console.log('  wr=', e.winRate, 'labels=', e.sourceTierLabels);
}
