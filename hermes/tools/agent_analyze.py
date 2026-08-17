#!/usr/bin/env python3
"""Agent Analyze — 组合选取与分析 Agent（全自动）

职责：
  1. 从数据池取 verified 数据（filter_verified）
  2. 调用 find_best_monotonic 选最优组合
  3. 可选：设计探针（委托 design_probes.design）
  4. 输出结构化 JSON 报告

安全：只读，不写任何文件。
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tools.data import pool
from tools.data.adapters import excel_target as et

FORBIDDEN_CMDS = ['git ', 'rm -rf', 'del /', 'checkout', 'reset', 'clean', 'restore']

# ── 探针设计 ──

def _fallback_probes(pool_records, targets):
    """按 WR 选5个配置作兜底探针。
    2026-08-06: W01(sd跨度)/W03(ratios多样性) 已移除——不再强制跨度/多样性，
    直接按 WR 降序取前 5 条（覆盖缺口段为主）。"""
    if not pool_records:
        return []
    # 按 WR 排序取 top 5
    candidates = sorted(pool_records, key=lambda r: r['wr'], reverse=True)
    probes = []
    for r in candidates[:5]:
        probes.append({
            'tier': 1, 'sd': int(r.get('sd', 0)), 'sc': int(r.get('sc', 5)),
            'ratios': str(r.get('ratios', '')), 'of': float(r.get('of', 0.5)),
            'predicted_wr': round(r['wr'], 1),
        })
    return probes


def _design_probes(level, targets, pool_records, difficulty):
    """委托 design_probes.design 实现完整探针设计。"""
    try:
        import os
        os.environ['DESIGN_PROBES_QUIET'] = '1'
        from tools.design_probes import design
        result = design(level)
        if isinstance(result, dict) and any(k.startswith('T') for k in result):
            return [result[k] for k in sorted(result.keys())]
    except Exception:
        pass
    return _fallback_probes(pool_records, targets)


# ── 组合选取 ──

def analyze_level(lv_str):
    """分析单关：取 verified 数据 → find_best_monotonic → 探针"""
    t = et.get_target(lv_str)
    if not t:
        return {'level': lv_str, 'error': 'no_targets'}

    recs = pool.get_all_records(lv_str)
    dedup = pool.dedup_records(recs)
    verified = pool.filter_verified(dedup)
    targets = t['tiers']

    result = {
        'level': lv_str,
        'difficulty': t.get('diff', 'normal'),
        'verified_count': len(verified),
        'total_records': len(dedup),
    }

    if len(verified) < 3:
        result['error'] = f'insufficient_verified_data ({len(verified)} records)'
        return result

    res = pool.find_best_monotonic(verified, targets, top_n=1, difficulty=t['diff'])
    if not res:
        result['error'] = 'find_best_monotonic failed'
        return result

    q, gs, best = res[0]
    tiers_out = []
    for i, r in enumerate(best):
        tiers_out.append({
            'tier': i+1, 'wr': round(r['wr'], 1),
            'diff': round(r['wr'] - targets[i], 1),
            'sd': str(r.get('sd', '')), 'sc': int(r.get('sc', 0)),
            'ratios': str(r.get('ratios', '')), 'of': float(r.get('of', 0)),
            'source': r.get('source', '?'), 'games': r.get('totalGames', 0),
        })

    result['combo'] = {
        'quality': round(q, 1), 'gaps': [round(g, 1) for g in gs],
        'tiers': tiers_out,
    }

    # 设计探针（备选）
    probes = _design_probes(lv_str, targets, verified, t['diff'])
    result['probe_count'] = len(probes)
    if probes:
        result['probes'] = probes

    return result


def main():
    parser = argparse.ArgumentParser(description='Agent Analyze — 组合选取分析')
    parser.add_argument('--levels', required=True)
    parser.add_argument('--filter-verified', action='store_true', default=True)
    parser.add_argument('--output', choices=['json', 'text'], default='json')
    args = parser.parse_args()

    levels = []
    for p in args.levels.split(','):
        p = p.strip()
        if '-' in p:
            a, b = p.split('-')
            levels.extend([str(i) for i in range(int(a), int(b)+1)])
        else:
            levels.append(p)

    results = [analyze_level(lv) for lv in levels]

    report = {
        'action': 'agent_analyze',
        'levels_requested': levels,
        'results': results,
        'status': 'ok',
    }

    if args.output == 'json':
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
    else:
        for r in results:
            c = r.get('combo')
            if c:
                wr = '/'.join(str(t['wr']) for t in c['tiers'])
                print(f"L{r['level']}: combo WR={wr}")
            else:
                print(f"L{r['level']}: {r.get('error','?')}")


if __name__ == '__main__':
    main()
