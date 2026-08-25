#!/usr/bin/env python3
"""Planner — 决策编排 Agent（编排层，不合并模块代码）

职责：串联 agent_analyze → judge_level → design_probes。
模块各自独立保留，可单独调用（手动调优也用）。
"""
import json, os, subprocess, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))


def action_for_judgment(judge_result, round_num, max_rounds=6):
    """Compatibility export of Judge's authoritative action mapping."""
    from tools.judge_level import action_for_judgment as _judge_action
    return _judge_action(judge_result, round_num, max_rounds)


def analyze_level(lv, include_probes=True):
    """分析单关：组合 → 判定 → 探针"""
    # 确保 tools 在 sys.path 中（被 subprocess 调用时）
    import sys
    _hermes = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _hermes not in sys.path:
        sys.path.insert(0, _hermes)
    result = {}

    # 1. agent_analyze（选组合，含 probes）
    aa = os.path.join(TOOLS, 'agent_analyze.py')
    env = os.environ.copy()
    env['DESIGN_PROBES_QUIET'] = '1'
    command = [sys.executable, aa, '--levels', str(lv), '--filter-verified', '--output', 'json']
    if not include_probes:
        command.append('--skip-probes')
    r = subprocess.run(
        command,
        capture_output=True, text=True, timeout=300, env=env
    )
    rc = r.returncode
    stdout = r.stdout.strip()
    result['agent_analyze_rc'] = rc

    if rc == 0 and stdout:
        try:
            data = json.loads(stdout)
            # agent_analyze 返回 {action, levels_requested, results: [{level, combo, probes, ...}]}
            results_list = data.get('results', [])
            if results_list:
                for k, v in results_list[0].items():
                    if k != 'level':
                        result[k] = v
            result['error'] = None
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            result['error'] = f'agent_analyze JSON parse failed: {e}'
    else:
        result['error'] = f'agent_analyze exit={rc}'

    # 2. 判定（judge_level 三态 + 轮次管理）
    if result.get('combo'):
        from tools.judge_level import MAX_ROUNDS, check_judgment, get_round
        from tools.data.adapters import excel_target as et
        t = et.get_target(lv)
        targets = t['tiers'] if t else None
        combo_wr = {f"T{ti['tier']}": ti['wr'] for ti in result['combo']['tiers']}
        judge_result, issues = check_judgment(combo_wr, result.get('difficulty', 'normal'), targets)
        result['judge'] = judge_result
        result['judge_issues'] = issues[:5]
        # 轮次管理
        rnd = get_round(lv)
        result['round'] = rnd
        result['max_rounds'] = MAX_ROUNDS
        result['action'] = action_for_judgment(judge_result, rnd, result['max_rounds'])
    else:
        result['judge'] = 'no_combo'

    # 3. 探针设计（AI 正式模式由 auto_loop 外层负责）
    if not include_probes:
        result['probes'] = []
        result['probe_count'] = 0
        result['probe_source'] = 'skipped_for_ai_selector'
    elif result.get('probes') and len(result['probes']) >= 5:
        result['probe_count'] = len(result['probes'])
        result['probe_source'] = 'agent_analyze'
    else:
        try:
            from tools.design_probes import design
            probes = design(lv)
            if isinstance(probes, dict) and any(k.startswith('T') for k in probes):
                result['probes'] = [probes[k] for k in sorted(probes.keys())]
            else:
                result['probes'] = []
        except Exception as e:
            result['probes'] = []
            result['probe_error'] = str(e)
        result['probe_count'] = len(result.get('probes', []))
        result['probe_source'] = 'planner_fallback'

    return result


def main():
    parser = argparse.ArgumentParser(description='Planner — 决策编排 Agent')
    parser.add_argument('--levels', required=True, help='关卡列表')
    parser.add_argument('--output', choices=['json', 'text'], default='json')
    parser.add_argument('--skip-probes', action='store_true',
                        help='只做组合分析，由外层 AI selector 负责探针设计')
    args = parser.parse_args()

    levels = []
    for p in args.levels.split(','):
        p = p.strip()
        if '-' in p:
            a, b = p.split('-')
            levels.extend([str(i) for i in range(int(a), int(b) + 1)])
        else:
            levels.append(p)

    results = {}
    for lv in levels:
        results[lv] = analyze_level(lv, include_probes=not args.skip_probes)

    if args.output == 'json':
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for lv, r in results.items():
            combo_str = '/'.join(f"{ti['wr']:.1f}" for ti in r.get('combo', {}).get('tiers', []))
            print(f"L{lv}: {r.get('judge', '?')} probes={r.get('probe_count', 0)} combo={combo_str}")


if __name__ == '__main__':
    import argparse
    main()