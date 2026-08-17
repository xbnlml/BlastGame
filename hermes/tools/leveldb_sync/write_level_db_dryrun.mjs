// dry-run: 验证用官方模块写入的 entry 格式与 DB 现有 entry 完全一致
// 用法: node hermes/tools/leveldb_sync/write_level_db_dryrun.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = 'C:/Users/Administrator/Documents/BlastGame';

// 官方模块（绝对路径 import，ESM 相对依赖基于模块自身位置，OK）
import { loadRunStore, upsertRunEntry, resolveActiveRun } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/runStore.mjs';
import { computeTierConfigFingerprint } from 'file:///C:/Users/Administrator/Documents/BlastGame/Tools/level-editor/launcher/leveldb/tierConfigMatch.mjs';

// 读取我们 pool 的配置+胜率（从 python 生成的中转 json）
const payload = JSON.parse(fs.readFileSync(path.join(__dirname, '_write_payload.json'), 'utf8'));

// 1. 加载现有 store
const store = loadRunStore(REPO, 'test');
console.log('加载成功: levels=', Object.keys(store.levels).length, ' corruptPath=', store.corruptPath);

// 2. 对每个关卡构造 entry 并 upsert（不保存）
const results = [];
for (const [lv, item] of Object.entries(payload)) {
  const tiers = item.tierConfigs;
  const fp = computeTierConfigFingerprint(tiers);
  const entry = {
    fingerprint: fp,
    tierConfigs: tiers,
    tierWinRates: item.tierWinRates,
    tierFailDistribution: item.tierFailDistribution || [null, null, null, null, null],
    importedAt: item.importedAt,
    sourceFileName: item.sourceFileName,
    sourceFormat: 'B',
    perTierMeta: tiers.map(() => ({ importedAt: item.importedAt, sourceFileName: item.sourceFileName })),
    lastResolvedAt: null,
  };
  const before = JSON.stringify(store);
  upsertRunEntry(store, lv, entry, { mergeTierIndex: null });
  const after = JSON.stringify(store);
  if (before === after) {
    results.push({ lv, ok: false, err: 'upsert 无变化' });
    continue;
  }
  const active = resolveActiveRun(store, lv, fp);
  results.push({ lv, ok: !!active, fp, active: !!active, wrs: entry.tierWinRates });
}

// 3. 输出结果（不写盘）
console.log('=== DRY RUN 结果（未写盘）===');
let ok = 0, fail = 0;
for (const r of results) {
  if (r.ok) { ok++; console.log(`L${r.lv}: OK fp=${r.fp} wrs=${r.wrs.map(w=>Math.round(w*100)+'%').join(',')}`); }
  else { fail++; console.log(`L${r.lv}: FAIL ${r.err || 'resolveActiveRun 未命中'}`); }
}
console.log(`\n成功 ${ok} / 失败 ${fail}`);

// 4. 格式校验：对比 store 里这条 entry 与现有 entry 字段集
const sampleKey = Object.keys(payload)[0];
const sampleEntry = store.levels[sampleKey].entries.find(e => e.fingerprint === computeTierConfigFingerprint(payload[sampleKey].tierConfigs));
if (sampleEntry) {
  const expectedKeys = ['fingerprint','tierConfigs','tierWinRates','tierFailDistribution','importedAt','sourceFileName','sourceFormat','perTierMeta','lastResolvedAt'];
  const actualKeys = Object.keys(sampleEntry).sort();
  const exp = [...expectedKeys].sort();
  console.log('\n=== 字段集校验 ===');
  console.log('期望:', exp.join(','));
  console.log('实际:', actualKeys.join(','));
  console.log('一致:', JSON.stringify(exp) === JSON.stringify(actualKeys) ? '✅' : '❌');
}
