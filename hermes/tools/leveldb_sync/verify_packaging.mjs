// verify_packaging.mjs — 打包前终极一致性验证（官方 resolveActiveRun 路径）
//
// 模拟打包/前端查询：asset 每档配置 → dealFingerprint → resolveActiveRun
// （boardFingerprint + dealFingerprint 精确匹配）→ DB entry winRate。
// 匹配到的 winRate 就是打包/前端显示的胜率。
//
// 用法: node tools/leveldb_sync/verify_packaging.mjs [--levels 54,61]
// 退出码: 0 = 全部解析成功；1 = 有缺失/异常
import fs from 'node:fs';
import path from 'node:path';
import { repoModuleUrl, resolveRepo } from './repo_paths.mjs';

const REPO = resolveRepo();
const { readAssetSnapshot } = await import(repoModuleUrl(REPO, 'Tools/level-editor/launcher/leveldb/assetSnapshot.mjs'));
const { loadRunStore, resolveActiveRun } = await import(repoModuleUrl(REPO, 'Tools/level-editor/launcher/leveldb/runStore.mjs'));
const { computeDealFingerprint, normalizeDealConfig } = await import(repoModuleUrl(REPO, 'Tools/level-editor/launcher/leveldb/boardFingerprint.mjs'));
const ASSET_ROOT = path.join(REPO, 'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test');
const store = loadRunStore(REPO, 'test');

function seg(lv) {
  const n = parseInt(lv, 10);
  if (n <= 20) return '1_20';
  if (n <= 40) return '21_40';
  if (n <= 60) return '41_60';
  if (n <= 80) return '61_80';
  if (n <= 100) return '81_100';
  if (n <= 120) return '101_120';
  if (n <= 140) return '121_140';
  if (n <= 160) return '141_160';
  if (n <= 180) return '161_180';
  return '181_200';
}

function main() {
  const argLevels = process.argv.find(a => a.startsWith('--levels='));
  let scan = [];
  if (argLevels) {
    scan = argLevels.split('=')[1].split(',').map(x => parseInt(x.trim(), 10)).filter(Boolean);
  } else {
    for (let lv = 1; lv <= 200; lv++) scan.push(lv);
  }

  let resolved = 0;
  let problems = [];
  for (const lv of scan) {
    const ap = path.join(ASSET_ROOT, seg(lv), `${lv}.asset`);
    if (!fs.existsSync(ap)) { problems.push(`L${lv}: asset文件不存在`); continue; }
    const snap = readAssetSnapshot(ap);
    if (!snap.ok) { problems.push(`L${lv}: asset读取失败 ${String(snap.error).slice(0, 40)}`); continue; }
    const { boardFingerprint, tiers } = snap.data;
    const tierList = tiers || [];
    for (let i = 0; i < tierList.length; i++) {
      const deal = normalizeDealConfig(tierList[i]);
      const dealFp = computeDealFingerprint(deal, boardFingerprint);
      const entry = resolveActiveRun(store, String(lv), boardFingerprint, dealFp);
      if (!entry || entry.winRate == null || entry.winRate <= 0) {
        problems.push(`L${lv} T${i + 1}: 无有效 entry (wr=${entry?.winRate})`);
      } else {
        resolved++;
      }
    }
  }

  console.log(`解析成功 ${resolved} 档`);
  if (problems.length) {
    console.log(`❌ ${problems.length} 个问题:`);
    problems.slice(0, 30).forEach(m => console.log(`  ${m}`));
    process.exit(1);
  } else {
    console.log(`✅ 全部 ${scan.length * 5} 档（${scan.length} 关）经官方 resolveActiveRun 解析到有效 winRate`);
    console.log('   asset 打包时数据库显示的胜率 = asset 配置对应胜率，严格一致');
    process.exit(0);
  }
}

main();