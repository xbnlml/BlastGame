"""Compare external optimizer data (51-100) with pool data."""

import csv
import json
import os
import sys
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
if str(HERMES) not in sys.path:
    sys.path.insert(0, str(HERMES))
from tools.data import pool

REPO = Path(os.environ.get('BLASTGAME_REPO', Path.home() / 'Documents' / 'BlastGame'))
EXTERNAL_DIR = str(REPO / 'telemetry' / 'bot' / '51-100-2026-07-24T11-40-09')
CSV_PATH = os.path.join(EXTERNAL_DIR, 'summary-51-100.csv')
STATUS_CSV_PATH = os.path.join(EXTERNAL_DIR, 'summary-level-status-51-100.csv')

# Read level status (comma delimited)
level_status = {}
with open(STATUS_CSV_PATH, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if len(row) >= 3:
            level_status[row[1].strip()] = row[2].strip()

# Read external summary (comma delimited)
external_data = {}
with open(CSV_PATH, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if len(row) < 27:
            continue
        level = row[0].strip()
        tier = row[2].strip()
        verified_wr = float(row[12]) if row[12] else 0.0
        sd = row[22].strip()
        sc = row[23].strip()
        ratios = row[24].strip()
        of = row[25].strip()
        
        if level not in external_data:
            external_data[level] = {}
        external_data[level][tier] = {
            'wr': verified_wr * 100,
            'sd': sd, 'sc': sc, 'ratios': ratios, 'of': of,
        }

def norm_of(v):
    try: return str(float(v))
    except: return v

def config_key(rec):
    return (str(rec.get('sd', '')), str(rec.get('sc', '')), str(rec.get('ratios', '')), norm_of(rec.get('of', '')))

# Get pool data
pool_data = {}
for lv in range(51, 101):
    lv_str = str(lv)
    try:
        pool_data[lv_str] = pool.get_preferred_records(lv_str)
    except Exception as e:
        print(f"Error loading pool data for level {lv}: {e}", file=sys.stderr)
        pool_data[lv_str] = []

TIER_ORDER = ['T1-超高胜率', 'T2-高胜率', 'T3-中等胜率', 'T4-低胜率', 'T5-超低胜率']
TIER_SHORT = {'T1-超高胜率': 'T1', 'T2-高胜率': 'T2', 'T3-中等胜率': 'T3', 'T4-低胜率': 'T4', 'T5-超低胜率': 'T5'}

results = []
for lv in [str(v) for v in range(51, 101)]:
    ext = external_data.get(lv, {})
    pool_recs = pool_data.get(lv, [])
    status = level_status.get(lv, 'unknown')
    
    if not ext:
        results.append({'level': lv, 'status': status, 'tier': 'N/A', 'ext_wr': 'N/A', 'pool_wr': 'N/A',
                        'ext_config': 'N/A', 'pool_config': 'N/A', 'config_match': 'N/A', 'wr_match': 'N/A'})
        continue
    
    for tier in TIER_ORDER:
        if tier not in ext:
            continue
        ext_rec = ext[tier]
        tier_short = TIER_SHORT[tier]
        
        matching_pool = [r for r in pool_recs if r.get('tier', '').startswith(tier_short)]
        best_pool = max(matching_pool, key=lambda r: r.get('wr', 0)) if matching_pool else None
        
        ext_wr_pct = ext_rec['wr']
        ext_config = f"{ext_rec['sd']}s/{ext_rec['sc']}c/{ext_rec['ratios']}r/{norm_of(ext_rec['of'])}of"
        ext_ck = config_key(ext_rec)
        config_match = any(config_key(r) == ext_ck for r in pool_recs)
        
        if best_pool:
            pool_wr = best_pool.get('wr', 0)
            pool_config = f"{best_pool.get('sd','?')}s/{best_pool.get('sc','?')}c/{best_pool.get('ratios','?')}r/{norm_of(best_pool.get('of','?'))}of"
            wr_diff = abs(pool_wr - ext_wr_pct)
            wr_match = wr_diff < 1.0
        else:
            pool_wr = 'N/A'
            pool_config = 'N/A'
            wr_match = False
        
        results.append({
            'level': lv, 'status': status, 'tier': tier,
            'ext_wr': f"{ext_wr_pct:.1f}%",
            'pool_wr': f"{pool_wr:.1f}%" if isinstance(pool_wr, (int, float)) else 'N/A',
            'ext_config': ext_config, 'pool_config': pool_config,
            'config_match': 'Y' if config_match else 'N',
            'wr_match': 'Y' if wr_match else 'N',
        })

# ── Print table ──
print("=" * 130)
print("COMPARISON: External Optimizer (51-100) vs Pool Data")
print("=" * 130)
print(f"{'Lv':>4} {'Status':>8} {'Tier':<14} {'ExtWR':>7} {'PoolWR':>7} {'CfgMatch':>9} {'WRMatch':>8} | Config")
print("-" * 130)
for r in results:
    if r['tier'] == 'N/A':
        print(f"{r['level']:>4} {r['status']:>8} {'N/A':<14} {'N/A':>7} {'N/A':>7} {'N/A':>9} {'N/A':>8} | No data")
    else:
        print(f"{r['level']:>4} {r['status']:>8} {r['tier']:<14} {r['ext_wr']:>7} {r['pool_wr']:>7} {r['config_match']:>9} {r['wr_match']:>8} | Ext:{r['ext_config']} | Pool:{r['pool_config']}")

# ── Summary ──
ok_results = [r for r in results if r['status'] == 'ok' and r['tier'] != 'N/A']
failed_levels = set(lv for lv in [str(v) for v in range(51, 101)] if level_status.get(lv) == 'failed')
ok_levels = set(r['level'] for r in results if r['status'] == 'ok')
no_data_levels = set(lv for lv in [str(v) for v in range(51, 101)] if lv not in external_data and lv not in failed_levels)

config_matches = sum(1 for r in ok_results if r['config_match'] == 'Y')
wr_matches = sum(1 for r in ok_results if r['wr_match'] == 'Y')
total_ok_tiers = len(ok_results)

levels_all_match = 0
levels_some_diff = 0
for lv in sorted(ok_levels):
    lv_results = [r for r in ok_results if r['level'] == lv]
    all_cfg_match = all(r['config_match'] == 'Y' for r in lv_results)
    all_wr_match = all(r['wr_match'] == 'Y' for r in lv_results)
    if all_cfg_match and all_wr_match:
        levels_all_match += 1
    else:
        levels_some_diff += 1

print()
print("=" * 130)
print("SUMMARY")
print("=" * 130)
print(f"Levels 51-100 total:                 {50}")
print(f"Optimizer succeeded (has data):      {len(ok_levels)} levels ({total_ok_tiers} tiers)")
print(f"Optimizer FAILED:                    {len(failed_levels)} levels")
print(f"Config matches (ok tiers):           {config_matches}/{total_ok_tiers} ({100*config_matches//total_ok_tiers}%)")
print(f"WR matches (<1% diff, ok tiers):     {wr_matches}/{total_ok_tiers} ({100*wr_matches//total_ok_tiers}%)")
print(f"Levels where ALL tiers match:        {levels_all_match}")
print(f"Levels with SOME diff:               {levels_some_diff}")

# Matches breakdown
print()
print("MATCH BREAKDOWN:")
print("-" * 130)
print(f"Config+WR both match: {sum(1 for r in ok_results if r['config_match']=='Y' and r['wr_match']=='Y')} tiers")
print(f"Config match, WR diff: {sum(1 for r in ok_results if r['config_match']=='Y' and r['wr_match']=='N')} tiers")
print(f"Config diff, WR diff:  {sum(1 for r in ok_results if r['config_match']=='N' and r['wr_match']=='N')} tiers")

# Failed levels
print()
print("FAILED LEVELS (no optimizer data):")
print("-" * 130)
failed_list = [lv for lv in [str(v) for v in range(51, 101)] if level_status.get(lv) == 'failed']
print(f"  {', '.join(failed_list)}")

# Levels with config differences
print()
print("LEVELS WITH CONFIG MISMATCHES (ext config not in pool):")
print("-" * 130)
config_diff_levels = sorted(set(r['level'] for r in ok_results if r['config_match'] == 'N'))
if config_diff_levels:
    for lv in config_diff_levels:
        tiers = [r['tier'] for r in ok_results if r['level'] == lv and r['config_match'] == 'N']
        print(f"  Level {lv}: {', '.join(tiers)}")
else:
    print("  None")

# Levels where WR differs significantly
print()
print("LEVELS WITH WR DIFFERENCES (≥1pp):")
print("-" * 130)
for lv in sorted(ok_levels):
    lv_results = [r for r in ok_results if r['level'] == lv]
    wr_diffs = [r for r in lv_results if r['wr_match'] == 'N']
    if wr_diffs:
        print(f"  Level {lv}:")
        for r in wr_diffs:
            print(f"    {r['tier']}: Ext={r['ext_wr']} Pool={r['pool_wr']}")