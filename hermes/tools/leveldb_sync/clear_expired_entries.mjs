// 清理 LevelDatabase 中 cutoff 前的过期 entries；默认只读，--apply 才写入。
// 用法：node tools/leveldb_sync/clear_expired_entries.mjs --levels 51-150 --dry-run
//      node tools/leveldb_sync/clear_expired_entries.mjs --levels 51-150 --apply
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { repoModuleUrl, resolveRepo } from './repo_paths.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = resolveRepo();
const RUN_PATH = path.join(REPO, 'LevelDatabase', 'Run', 'test.json');
const BACKUP_DIR = path.join(REPO, 'LevelDatabase', 'Backups');
const DEFAULT_CUTOFF = '2026-08-13T06:36:00Z'; // 2026-08-13 14:36 +08:00

const { loadRunStore, saveRunStore } = await import(repoModuleUrl(REPO, 'Tools/level-editor/launcher/leveldb/runStore.mjs'));

function parseArgs(argv) {
  const out = { levels: null, cutoff: DEFAULT_CUTOFF, apply: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--levels') out.levels = argv[++i];
    else if (a === '--cutoff') out.cutoff = argv[++i];
    else if (a === '--apply') out.apply = true;
    else if (a === '--dry-run') out.apply = false;
    else if (a === '--help' || a === '-h') {
      console.log('用法: node clear_expired_entries.mjs --levels 51-150 [--dry-run|--apply] [--cutoff ISO]');
      process.exit(0);
    } else throw new Error(`未知参数: ${a}`);
  }
  if (!out.levels) throw new Error('--levels 必填');
  return out;
}

function parseLevels(spec) {
  const out = new Set();
  for (const raw of String(spec).split(',')) {
    const part = raw.trim();
    if (!part) continue;
    if (/^\d+-\d+$/.test(part)) {
      const [a, b] = part.split('-').map(Number);
      for (let n = a; n <= b; n++) out.add(String(n));
    } else if (/^\d+$/.test(part)) {
      out.add(String(Number(part)));
    } else throw new Error(`非法关卡: ${part}`);
  }
  return [...out].sort((a, b) => Number(a) - Number(b));
}

function parseTimestamp(value) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  // 项目旧记录中的无时区时间按中国标准时间解释，避免机器时区影响边界。
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}+08:00`;
  const ms = Date.parse(normalized);
  return Number.isFinite(ms) ? ms : null;
}

function entryTimestamp(entry) {
  return entry?.importedAt ?? entry?.perResultMeta?.importedAt ?? entry?.createdAt ?? null;
}

function classify(entry, cutoffMs) {
  const raw = entryTimestamp(entry);
  const ms = parseTimestamp(raw);
  if (ms === null) return 'unknown';
  return ms < cutoffMs ? 'expired' : 'fresh';
}

function summarize(store, levels, cutoffMs) {
  const summary = { total: 0, expired: 0, fresh: 0, unknown: 0, changedLevels: [] };
  for (const lv of levels) {
    const entries = store.levels?.[lv]?.entries ?? [];
    let expired = 0;
    let fresh = 0;
    let unknown = 0;
    for (const entry of entries) {
      const kind = classify(entry, cutoffMs);
      summary.total++;
      summary[kind]++;
      if (kind === 'expired') expired++;
      else if (kind === 'fresh') fresh++;
      else unknown++;
    }
    if (expired) summary.changedLevels.push({ lv, total: entries.length, expired, fresh, unknown });
  }
  return summary;
}

function printSummary(summary, cutoff, apply) {
  console.log(`${apply ? 'APPLY' : 'DRY-RUN'}: cutoff=${cutoff}`);
  console.log(`范围 entries=${summary.total} 过期=${summary.expired} 保留=${summary.fresh} 未知保留=${summary.unknown}`);
  for (const row of summary.changedLevels) {
    console.log(`  L${row.lv}: ${row.expired} 删除 / ${row.fresh} 保留 / ${row.unknown} 未知保留`);
  }
}

function backupRunFile() {
  fs.mkdirSync(BACKUP_DIR, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backup = path.join(BACKUP_DIR, `pre_clear_expired_test_${stamp}.json`);
  fs.copyFileSync(RUN_PATH, backup);
  if (!fs.existsSync(backup) || fs.statSync(backup).size === 0) {
    throw new Error(`备份验证失败: ${backup}`);
  }
  console.log(`写前备份: ${backup}`);
  return backup;
}

const args = parseArgs(process.argv.slice(2));
const levels = parseLevels(args.levels);
const cutoffMs = parseTimestamp(args.cutoff);
if (cutoffMs === null) throw new Error(`非法 cutoff: ${args.cutoff}`);

const store = loadRunStore(REPO, 'test');
const before = summarize(store, levels, cutoffMs);
printSummary(before, args.cutoff, args.apply);

if (!args.apply) process.exit(0);

backupRunFile();
for (const lv of levels) {
  const node = store.levels?.[lv];
  if (!node?.entries?.length) continue;
  node.entries = node.entries.filter(entry => classify(entry, cutoffMs) !== 'expired');
}
saveRunStore(REPO, store);
console.log('已保存: LevelDatabase/Run/test.json');

const verifyStore = loadRunStore(REPO, 'test');
const after = summarize(verifyStore, levels, cutoffMs);
printSummary(after, args.cutoff, true);
if (after.expired !== 0) throw new Error(`回读验证失败：仍有 ${after.expired} 条过期 entry`);
if (after.fresh !== before.fresh) throw new Error(`回读验证失败：新 entry 数量 ${before.fresh} -> ${after.fresh}`);
if (after.unknown !== before.unknown) throw new Error(`回读验证失败：未知 entry 数量 ${before.unknown} -> ${after.unknown}`);
console.log('✅ DB 过期 entry 清理及新数据保留验证通过');
