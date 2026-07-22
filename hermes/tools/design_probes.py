#!/usr/bin/env python3
"""自动设计探针配置。

逻辑: 遍历 phase2 候选，逐一加入 bot400 池，看哪个对整体 5 档结构提升最大。
不盯档位，只看池子整体。

用法:
  python design_probes.py 77                 # L77
  python design_probes.py 77 --write         # 写入 probe_configs.json
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROBE_CFG = os.path.join(TOOLS_DIR, 'probe_configs.json')
from tools.data import pool
from tools.data.adapters import excel_target as et


def design(lv):
    targets = et.get_target(lv)
    if not targets:
        print(f'L{lv}: no targets')
        return None
    targets = targets['tiers']
    
    # Get all data
    recs = pool.get_preferred_records(str(lv))
    uniq = pool.dedup_records(recs)
    bot400 = [r for r in uniq if r.get('source') == 'bot' and r.get('totalGames', 0) >= 400]
    phase2 = [r for r in uniq if r.get('source') in ('phase2', 'phase1') and r.get('totalGames', 0) >= 100]
    
    if len(bot400) < 3:
        print(f'L{lv}: bot400 不足 ({len(bot400)}条)，直接探 all phase2')
        return None

    # Baseline: best combo from bot400 only
    bot_min = min(r['wr'] for r in bot400)
    bot_max = max(r['wr'] for r in bot400)
    base_results = pool.find_best_monotonic(bot400, targets)
    print(f'L{lv}: bot400={len(bot400)}条 WR范围={bot_min:.0f}~{bot_max:.0f}%')

    if base_results:
        base_score, base_gaps, base_recs = base_results[0]
        base_wrs = [r['wr'] for r in base_recs]
        print(f'  baseline score={base_score:.0f} WRs={" ".join(f"{w:.0f}" for w in base_wrs)} gaps={" ".join(f"{g:.0f}" for g in base_gaps)}')
    else:
        base_score, base_recs = None, None
        print(f'  baseline: 无合格组合')
    
    # Try each phase2 candidate
    candidates = []
    for p in phase2:
        key = p['sd'] + '|' + (p.get('ratios','') or '')
        # Skip if already in bot400
        if any(bp['sd'] == p['sd'] and bp.get('ratios','') == p.get('ratios','') for bp in bot400):
            continue
        
        test_pool = bot400 + [p]
        test_results = pool.find_best_monotonic(test_pool, targets)
        if test_results:
            score, gaps, recs = test_results[0]
            if base_recs is None or score < base_score:
                in_range = bot_min <= p['wr'] <= bot_max
                improvement = (base_score - score) if base_recs else 999
                candidates.append({
                    'sd': p['sd'], 'sc': p.get('sc',5), 'ratios': p.get('ratios',''), 'of': p.get('of',0.5),
                    'wr': p['wr'], 'score': score, 'improvement': improvement,
                    'in_range': in_range, 'source': p.get('source','')
                })
    
    # Sort: in-range candidates first, then by improvement
    candidates.sort(key=lambda c: (0 if c['in_range'] else 1, -c['improvement']))
    
    if candidates:
        print(f'  phase2候选: {len(candidates)}个有用')
        for c in candidates[:7]:
            r = '范围内' if c['in_range'] else '范围外'
            s,ra,o,w,im = c["sd"],c["ratios"],c["of"],c["wr"],c["improvement"]
            print("    sd=%s rat=%s of=%s WR≈%d%% (%s) +%d分" % (str(s).rjust(3), str(ra).rjust(20), str(o).rjust(4), int(w), r, int(im)))

        # Generate probes: top 5 (prefer in-range)
        probes = [c for c in candidates if c['in_range']][:3] + [c for c in candidates if not c['in_range']][:2]
        probes = probes[:5]
        
        return _make_config(probes, targets, bot_min, bot_max)
    else:
        print('  phase2: 无可提升的候选')
        return None


def _design_probe(wr, bot_min, bot_max):
    """自设计一个探针配置（phase2无合适候选时用）"""
    # 在已有范围内用sd估算，范围外用边界
    in_range = bot_min <= wr <= bot_max
    if in_range:
        sd = 35 - int(wr * 0.4)  # 粗略反推: WR越高sd越低
    else:
        sd = 5 if wr > bot_max else 40  # 范围外：高WR用低sd，低WR用高sd
    sd = max(0, min(45, sd))
    return {'sd': sd, 'sc': 5, 'ratios': '1,1,1,1,1', 'of': 0.5}


def _estimate_sd(wr_target):
    """根据目标WR估算初始sd（粗略）"""
    if wr_target >= 90: return 0
    if wr_target >= 80: return 5
    if wr_target >= 70: return 10
    if wr_target >= 60: return 15
    if wr_target >= 50: return 20
    if wr_target >= 40: return 30
    if wr_target >= 30: return 35
    return 40

def _design_placeholder(gap_wr, bot_min, bot_max):
    """phase2无合适候选时，自设计一个探针配置"""
    sd = _estimate_sd(gap_wr)
    # Use all-1 ratios (most neutral), sc=5
    return {'sd': sd, 'sc': 5, 'ratios': '1,1,1,1,1', 'of': 0.5}

def _make_config(probes, targets, bot_min, bot_max):
    """生成 5 槽探针配置（phase2候选 + 自设计混合）"""
    result = []
    for p in probes:
        result.append({
            'sd': int(p['sd']), 'sc': int(p.get('sc',5)),
            'ratios': p['ratios'], 'of': float(p.get('of', 0.5))
        })
    while len(result) < 5:
        # Fill with designed probes
        gap_wr = (bot_max - bot_min) * (1 - len(result)/5) + bot_min
        result.append(_design_probe(gap_wr, bot_min, bot_max))
    out = {}
    for i, r in enumerate(result):
        out[f'T{i+1}'] = r
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('spec')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    
    levels = set()
    for part in args.spec.split(','):
        if '-' in part:
            a,b = part.split('-')
            levels.update(str(i) for i in range(int(a), int(b)+1))
        else:
            levels.add(part)
    
    for lv in sorted(levels, key=int):
        probes = design(str(lv))
        if probes is not None and len(probes) > 0 and args.write:
            cfg = json.load(open(PROBE_CFG))
            cfg[str(lv)] = probes
            json.dump(cfg, open(PROBE_CFG,'w'), indent=2, ensure_ascii=False)
            print(f'  -> written')


if __name__ == '__main__':
    main()
