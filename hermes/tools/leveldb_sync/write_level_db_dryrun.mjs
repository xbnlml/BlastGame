// dry-run: 验证用官方模块写入的 entry 格式与 DB 现有 entry 完全一致
// 用法: node hermes/tools/leveldb_sync/write_level_db_dryrun.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = 'C:/Users/Administrator/Documents/BlastGame';

// 官方模块（绝对路径 import，ESM 相对依赖基于模块自身位置，OK）
import { loadRunStore, upsertRunEntry, resolveActiveRun } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/runStore.mjs';
import { computeDealConfigFingerprint } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/tierConfigMatch.mjs';
import { readAssetSnapshot } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/assetSnapshot.mjs';

// 读取我们 pool 的配置+胜率（从 python 生成的中转 json）
const payload = JSON.parse(fs.readFileSync(path.join(__dirname, '_write_payload.json'), 'utf8'));

// 1. 加载现有 store
const store = loadRunStore(REPO, 'test');
console.log('加载成功: levels=', Object.keys(store.levels).length, ' corruptPath=', store.corruptPath);

// 2. 对每个关卡按正式 write_level_db.mjs 的当前单档 entry 结构构造并 upsert（不保存）
const results = [];
for (const [lv, item] of Object.entries(payload)) {
  const tiers = item.tierConfigs;
  const levelNode = store.levels[String(lv)];
  if (levelNode?.entries?.length) levelNode.entries = [];
  const assetPath = findAssetPath(REPO, lv);
  if (!assetPath) {
    results.push({ lv, ok: false, err: 'asset 未找到' });
    continue;
  }
  const snap = readAssetSnapshot(assetPath);
  if (!snap.ok) {
    results.push({ lv, ok: false, err: 'asset 解析失败: ' + (snap.error || '') });
    continue;
  }
  const boardFingerprint = snap.data.boardFingerprint;
  const assetTiers = snap.data.tiers;
  const tierResults = [];
  for (let i = 0; i < tiers.length && i < 5; i++) {
    const dealConfig = normalizeConfig(tiers[i]);
    const dealFingerprint = computeDealConfigFingerprint(dealConfig);
    const matchedAssetSlots = [];
    for (let a = 0; a < assetTiers.length; a++) {
      if (sameConfig(dealConfig, assetTiers[a])) matchedAssetSlots.push(a);
    }
    const entry = {
      fingerprintAlgorithm: 'sha256-v1',
      boardFingerprint,
      dealFingerprint,
      fingerprint: dealFingerprint,
      identitySource: 'hermes-import',
      identityStatus: 'verified',
      dealConfig,
      matchedAssetSlots,
      winRate: item.tierWinRates[i] ?? null,
      failDistribution: item.tierFailDistribution?.[i] ?? null,
      sourceTierLabels: [['T1', 'T2', 'T3', 'T4', 'T5'][i]],
      perResultMeta: { importedAt: item.importedAt, sourceFileName: item.sourceFileName },
      importedAt: item.importedAt,
      sourceFileName: item.sourceFileName,
      sourceFormat: 'B',
      lastResolvedAt: null,
    };
    const stored = upsertRunEntry(store, lv, entry, { prune: false });
    const active = resolveActiveRun(store, lv, boardFingerprint, dealFingerprint);
    tierResults.push({
      tier: ['T1', 'T2', 'T3', 'T4', 'T5'][i],
      ok: !!stored && !!active && matchedAssetSlots.length > 0,
      fp: dealFingerprint.slice(0, 8),
      wr: item.tierWinRates[i] !== undefined ? Math.round(item.tierWinRates[i] * 100) + '%' : '—',
      matchedAssetSlots,
    });
  }
  results.push({ lv, ok: tierResults.length === 5 && tierResults.every((r) => r.ok), tiers: tierResults });
}

// 3. 输出结果（不写盘）
console.log('=== DRY RUN 结果（未写盘）===');
let ok = 0, fail = 0;
for (const r of results) {
  if (r.ok) { ok++; console.log(`L${r.lv}: OK ${r.tiers.map(t => t.tier + '=' + t.wr).join(',')}`); }
  else { fail++; console.log(`L${r.lv}: FAIL ${r.err || r.tiers?.filter(t => !t.ok).map(t => t.tier).join(',') || 'entry 验证失败'}`); }
}
console.log(`\n成功 ${ok} / 失败 ${fail}`);

function normalizeConfig(cfg) {
  const ratios = Array.isArray(cfg.shuffleSplitRatios)
    ? cfg.shuffleSplitRatios.join(',')
    : String(cfg.shuffleSplitRatios || '');
  return {
    startDifficulty: cfg.startDifficulty,
    shuffleSplitCount: cfg.shuffleSplitCount,
    shuffleSplitRatios: ratios,
    shuffleOverflowFactor: String(cfg.shuffleOverflowFactor ?? 0),
  };
}

function findAssetPath(repo, lv) {
  const n = parseInt(lv, 10);
  let seg;
  if (n <= 20) seg = '1_20';
  else if (n <= 40) seg = '21_40';
  else if (n <= 60) seg = '41_60';
  else if (n <= 80) seg = '61_80';
  else if (n <= 100) seg = '81_100';
  else if (n <= 120) seg = '101_120';
  else if (n <= 140) seg = '121_140';
  else if (n <= 160) seg = '141_160';
  else if (n <= 180) seg = '161_180';
  else seg = '181_200';
  for (const group of ['test', 'funnel_b']) {
    const candidate = path.join(repo, 'Assets', 'GameModule', 'GameMain', 'ConfigSo', 'Generated_enum', group, seg, `${lv}.asset`);
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function sameConfig(a, b) {
  return Number(a.startDifficulty) === Number(b.startDifficulty)
    && Number(a.shuffleSplitCount) === Number(b.shuffleSplitCount)
    && normalizeRatios(a.shuffleSplitRatios) === normalizeRatios(b.shuffleSplitRatios)
    && Math.abs(Number(a.shuffleOverflowFactor) - Number(b.shuffleOverflowFactor)) < 1e-6;
}

function normalizeRatios(raw) {
  return String(raw ?? '').trim().replace(/，/g, ',').split(',').map((x) => x.trim()).filter(Boolean).join(',');
}
