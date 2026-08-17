#!/usr/bin/env python3
"""Agent Review — 入库复核 Agent（全自动）

职责：
  1. 调用 judge_level.judge_with_rounds 做标准判定 + 6轮追踪
  2. 四元组验证：比对 asset 实际写入值
  3. Excel 目标一致性交叉校验
  4. 输出 pass/fail + round_info 结构化报告

安全：只读（除 _rounds.json 由 judge_level 管理），不写任何文件。
"""
import argparse, json, os, sys, time

ROOT = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tools.asset_patcher import read_ddc
from tools.data.adapters import excel_target as et


def check_gaps(tiers, difficulty, lv=None):
    """使用 judge_level.check_judgment 的标准判定。lv 传入时启用目标偏差软约束。"""
    combo = {f'T{i+1}': t['wr'] for i, t in enumerate(tiers)}
    from tools.judge_level import check_judgment
    targets = None
    if lv:
        t = et.get_target(lv)
        targets = t['tiers'] if t else None
    result, issues = check_judgment(combo, difficulty, targets)
    return [] if result == '合格' else issues


def check_targets(lv, tiers):
    """和 Excel 目标比对"""
    t = et.get_target(lv)
    if not t:
        return ['no_excel_target']
    issues = []
    for i, tier in enumerate(tiers):
        if i >= len(t['tiers']):
            break
        diff = tier['wr'] - t['tiers'][i]
        if abs(diff) > 10:  # 2026-08-10：判定收紧 15→10（对齐全绿标准）
            issues.append(f'T{i+1}: WR={tier["wr"]:.1f} target={t["tiers"][i]:.0f} diff={diff:.0f}pp')
    return issues


def review_level(lv, tiers, difficulty):
    """单关复核 — 委托 judge_with_rounds + asset 四元组检查"""
    from tools.judge_level import judge_with_rounds
    combo, result, reasons, ri = judge_with_rounds(int(lv))
    issues = list(reasons)
    passed = (result == '合格')

    # Asset 四元组校验
    try:
        asset_tiers = read_ddc(int(lv))
        for i in range(min(5, len(tiers), len(asset_tiers))):
            a = asset_tiers[i]
            t = tiers[i]
            for f in ('sd', 'sc', 'ratios', 'of'):
                ev = str(t.get(f, '')).strip()
                av = str(a.get(f, '')).strip()
                if not ev or not av:
                    continue
                try:
                    if abs(float(ev) - float(av)) < 0.001:
                        continue
                except:
                    pass
                if ev != av:
                    issues.append(f'T{i+1} {f}: expected={ev} asset={av}')
    except Exception as e:
        issues.append(f'asset_read_error: {e}')

    return {'level': str(lv), 'passed': passed and not issues,
            'issues': issues, 'result': result,
            'round_info': ri, 'difficulty': difficulty}


def main():
    parser = argparse.ArgumentParser(description='Agent Review — 入库复核')
    parser.add_argument('--combo-file', required=True, help='combo 方案 JSON 文件')
    parser.add_argument('--output', choices=['json', 'text'], default='json')
    args = parser.parse_args()

    # 加载 combo 文件，带重试
    plan = None
    for attempt in range(3):
        try:
            with open(args.combo_file, 'r', encoding='utf-8') as f:
                plan = json.load(f)
            break
        except (json.JSONDecodeError, FileNotFoundError) as e:
            if attempt < 2:
                time.sleep(1)
            else:
                report = {'action': 'agent_review', 'status': 'error',
                         'error': f'Cannot load combo file: {e}'}
                print(json.dumps(report, ensure_ascii=False))
                sys.exit(1)

    levels_data = plan.get('levels', {})
    results = []
    for lv_str, lv_data in levels_data.items():
        tiers = lv_data.get('tiers', [])
        difficulty = lv_data.get('difficulty', 'normal')
        results.append(review_level(lv_str, tiers, difficulty))

    all_pass = all(r['passed'] for r in results)
    report = {
        'action': 'agent_review',
        'levels_reviewed': len(results),
        'all_pass': all_pass,
        'results': results,
        'status': 'ok' if all_pass else 'fail',
    }

    if args.output == 'json':
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
    else:
        for r in results:
            status = 'PASS' if r['passed'] else 'FAIL'
            ri = r.get('round_info', {})
            print(f'L{r["level"]}: {status} ({r["difficulty"]}) r{ri.get("round","?")}/{ri.get("max","?")} {ri.get("action","")}')
            for issue in r['issues']:
                print(f'  - {issue}')


if __name__ == '__main__':
    main()
