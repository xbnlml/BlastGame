// 正式写入: 把我们验证过的数据写入关卡数据库 Run/test.json（单档 entry 结构）
// 用法: node hermes/tools/leveldb_sync/write_level_db.mjs
// 安全: 官方模块 saveRunStore = 自动备份(Backups/保留5) + 原子写(tmp+rename) + 稳定排序
// 2026-08-07 改造: 从"五档组合 entry"改为"逐档单档 entry"（对齐 DB 实际结构 + leveldb 重构后的单档 API）
//   - 每档用 computeDealConfigFingerprint 算单档 dealFingerprint
//   - boardFingerprint 从 asset 读牌面计算（同关卡所有档相同）
//   - 每档独立 upsert，保留分档修改记录
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { repoModuleUrl, resolveRepo } from './repo_paths.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = resolveRepo();

const { loadRunStore, upsertRunEntry, saveRunStore, resolveActiveRun } = await import(repoModuleUrl(REPO, 'Tools/level-editor/launcher/leveldb/runStore.mjs'));
const { computeDealConfigFingerprint } = await import(repoModuleUrl(REPO, 'Tools/level-editor/launcher/leveldb/tierConfigMatch.mjs'));
const { readAssetSnapshot } = await import(repoModuleUrl(REPO, 'Tools/level-editor/launcher/leveldb/assetSnapshot.mjs'));

const payload = JSON.parse(fs.readFileSync(path.join(__dirname, '_write_payload.json'), 'utf8'));

// 1. 写前备份 Run/test.json 到 Backups/（双保险，官方 saveRunStore 也会再备一份）
const bakDir = path.join(REPO, 'LevelDatabase', 'Backups');
fs.mkdirSync(bakDir, { recursive: true });
const runPath = path.join(REPO, 'LevelDatabase', 'Run', 'test.json');
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
fs.copyFileSync(runPath, path.join(bakDir, `pre_hermes_write_test_${stamp}.json`));
console.log('写前备份: Backups/pre_hermes_write_test_' + stamp + '.json');

// 2. 加载 store
const store = loadRunStore(REPO, 'test');
console.log('加载成功: levels=', Object.keys(store.levels).length);

// 3. upsert 全部 payload 关卡（逐档单档 entry）
const results = [];
for (const [lv, item] of Object.entries(payload)) {
  // 2026-08-18 修：写前清掉该关全部旧 entry（不只 hermes-import，含探针/老数据残留）——
  // 否则非 import 残留也占位，runStore 的 pruneOldEntries(maxEntries=8) 会把新 entry
  // 当旧挤掉（L54/72/134 补一档丢一档根因，L186 案例同因）。清空后写 5 档不触发 prune。
  const levelNode = store.levels[String(lv)];
  if (levelNode?.entries?.length) {
    levelNode.entries = [];
  }
  const tiers = item.tierConfigs;
  const winRates = item.tierWinRates;
  const tierLabels = ['T1', 'T2', 'T3', 'T4', 'T5'];
  // 读 asset 拿 boardFingerprint + 各档 dealFingerprint
  // asset 路径：按 test/分段 找（121_140 对应 L128）
  const assetRel = item.assetPath || findAssetPath(REPO, lv);
  if (!assetRel) {
    results.push({ lv, ok: false, err: 'asset 未找到' });
    continue;
  }
  const snap = readAssetSnapshot(assetRel);
  if (!snap.ok) {
    results.push({ lv, ok: false, err: 'asset 解析失败: ' + (snap.error || '') });
    continue;
  }
  const boardFingerprint = snap.data.boardFingerprint;
  const assetTiers = snap.data.tiers;
  const assetFps = snap.data.tierFingerprints;

  const lvResults = [];
  for (let i = 0; i < tiers.length && i < 5; i++) {
    const dealConfig = normalizeConfig(tiers[i]);
    const dealFingerprint = computeDealConfigFingerprint(dealConfig);
    // 找该配置匹配的 asset slot（matchedAssetSlots）
    const matchedSlots = [];
    for (let a = 0; a < assetTiers.length; a++) {
      if (sameConfig(dealConfig, assetTiers[a])) matchedSlots.push(a);
    }
    const entry = {
      fingerprintAlgorithm: 'sha256-v1',
      boardFingerprint,
      dealFingerprint,
      fingerprint: dealFingerprint,
      identitySource: 'hermes-import',
      identityStatus: 'verified',
      dealConfig,
      matchedAssetSlots: matchedSlots,
      winRate: winRates[i] ?? null,
      failDistribution: null,
      sourceTierLabels: [tierLabels[i] || ('T' + (i + 1))],
      perResultMeta: {
        importedAt: item.importedAt,
        sourceFileName: item.sourceFileName
      },
      importedAt: item.importedAt,
      sourceFileName: item.sourceFileName,
      sourceFormat: 'B',
      lastResolvedAt: null
    };
    const before = JSON.stringify(store.levels[String(lv)] ?? null);
    upsertRunEntry(store, lv, entry, { mergeTierIndex: null });
    const after = JSON.stringify(store.levels[String(lv)] ?? null);
    const active = resolveActiveRun(store, lv, boardFingerprint, dealFingerprint);
    lvResults.push({
      tier: tierLabels[i] || ('T' + (i + 1)),
      ok: before !== after && !!active,
      fp: dealFingerprint.slice(0, 8),
      dealFingerprint,
      wr: winRates[i] !== undefined ? Math.round(winRates[i] * 100) + '%' : '—'
    });
  }
  const allOk = lvResults.every(r => r.ok);
  results.push({ lv, ok: allOk, boardFingerprint, tiers: lvResults });
}

// 4. 保存（官方: 备份+原子写+稳定排序）
saveRunStore(REPO, store);
console.log('已保存: LevelDatabase/Run/test.json');

// 5. 回读验证
const verify = loadRunStore(REPO, 'test');
let vok = 0, vfail = 0;
for (const r of results) {
  if (!r.ok) { vfail++; console.log(`L${r.lv}: 写入失败`); continue; }
  const node = verify.levels[String(r.lv)];
  let tierOk = 0;
  for (const t of r.tiers) {
    // Normal 的 T1=T2/T4=T5 是合法的配置去重，不能按 sourceTierLabels
    // 要求五条独立 entry；按官方活动 fingerprint 逐档回读。
    const e = resolveActiveRun(verify, String(r.lv), r.boardFingerprint, t.dealFingerprint);
    if (e && e.winRate !== undefined) tierOk++;
  }
  if (tierOk >= 5) {
    vok++;
    console.log(`L${r.lv}: 验证通过（${r.tiers.map(t => t.tier + '=' + t.wr).join(', ')}）`);
  } else {
    vfail++;
    console.log(`L${r.lv}: 部分验证失败（${tierOk}/5 档）`);
  }
}
console.log(`\n写入 ${results.length} 关, 回读验证 ${vok} 通过 / ${vfail} 失败`);
process.exit(vfail > 0 ? 1 : 0);

// ===== helpers =====
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
  const candidates = [
    path.join(repo, 'Assets', 'GameModule', 'GameMain', 'ConfigSo', 'Generated_enum', 'test', seg, lv + '.asset'),
    path.join(repo, 'Assets', 'GameModule', 'GameMain', 'ConfigSo', 'Generated_enum', 'funnel_b', seg, lv + '.asset')
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  // 兜底 os.walk
  const roots = [path.join(repo, 'Assets')];
  for (const root of roots) {
    const found = walkFind(root, lv + '.asset');
    if (found) return found;
  }
  return null;
}

function walkFind(dir, target) {
  if (!fs.existsSync(dir)) return null;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      const r = walkFind(p, target);
      if (r) return r;
    } else if (e.name === target) {
      return p;
    }
  }
  return null;
}

function normalizeConfig(cfg) {
  // ratios 数组 → 字符串（DB 存字符串）
  const ratios = Array.isArray(cfg.shuffleSplitRatios)
    ? cfg.shuffleSplitRatios.join(',')
    : String(cfg.shuffleSplitRatios || '');
  return {
    startDifficulty: cfg.startDifficulty,
    shuffleSplitCount: cfg.shuffleSplitCount,
    shuffleSplitRatios: ratios,
    shuffleOverflowFactor: String(cfg.shuffleOverflowFactor ?? 0)
  };
}

function sameConfig(a, b) {
  try {
    return Number(a.startDifficulty) === Number(b.startDifficulty) &&
      Number(a.shuffleSplitCount) === Number(b.shuffleSplitCount) &&
      normalizeRatioKey(String(a.shuffleSplitRatios)) === normalizeRatioKey(String(b.shuffleSplitRatios)) &&
      floatEq(a.shuffleOverflowFactor, b.shuffleOverflowFactor);
  } catch {
    return false;
  }
}

function normalizeRatioKey(raw) {
  return String(raw ?? '').trim().replace(/，/g, ',').split(',').map(s => s.trim()).filter(Boolean).join(',');
}

function floatEq(a, b) {
  return Math.abs(Number(a) - Number(b)) < 1e-6;
}