#!/usr/bin/env python3
"""全局状态快照 — 一行一关卡，显示当前状态、best WR、gap、死亡分布。

用法:
  python tools/state_snapshot.py
  python tools/state_snapshot.py --levels 82,98
  python tools/state_snapshot.py --pending   # 只看待调优
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))


def get_board_levels():
    """读取 board.md"""
    bp = os.path.join(TOOL_DIR, '..', 'project-state', 'board.md')
    if not os.path.exists(bp):
        return {}, {}, {}
    done, retired, pending = {}, {}, {}
    section = None
    with open(bp, encoding='utf-8') as f:
        for line in f:
            if '入库' in line:
                section = 'done'
                continue
            elif '改关卡' in line:
                section = 'retired'
                continue
            elif '空白' in line or '待选' in line or '待调优' in line:
                section = 'pending'
                continue
            if section and line.strip() and '---' not in line and '#' not in line:
                for w in line.replace(',', ' ').split():
                    try:
                        lv = int(w)
                        if 51 <= lv <= 200:
                            targets = {
                                'done': done,
                                'retired': retired,
                                'pending': pending,
                            }[section]
                            targets[lv] = line.strip()
                    except ValueError:
                        pass
    return done, retired, pending


def main(level_filter=None, mode='all'):
    from tools.data import pool as pool_mod
    from tools.data.adapters import excel_target as et

    done, retired, pending = get_board_levels()

    # 收集所有有关卡编号
    all_levels = set()
    all_levels.update(done.keys())
    all_levels.update(retired.keys())
    all_levels.update(pending.keys())

    if level_filter:
        all_levels = {lv for lv in all_levels if lv in level_filter}
    if mode == 'pending':
        all_levels = {lv for lv in all_levels if lv in pending}

    if not all_levels:
        print('❌ 无关卡数据')
        return

    # 每关查池子
    print(f'{"关":>4} {"状态":>8} {"档":>4} {"WR":>6} {"目标差":>6} {"sd":>4} {"ratios":<18} {"of":>6} {"来源":>6} {"死亡分布":<20} {"gaps":<18}')
    print('-' * 110)

    for lv in sorted(all_levels):
        if lv in done:
            status = '🟢入库'
        elif lv in retired:
            status = '❌改关卡'
        elif lv in pending:
            status = '🟡待调优'
        else:
            status = '⚪未知'

        # 查目标
        t = et.get_target(lv)
        if not t:
            print(f'  {lv:>3} {status:>8}  — 无目标配置')
            continue
        targets = t['tiers']
        diff_label = {0: 'N', 1: 'H', 2: 'SH'}.get(t.get('diff_type', t.get('diff', '')), '?')

        # 查最佳组合
        recs = pool_mod.dedup_records(pool_mod.get_preferred_records(str(lv)))
        result = pool_mod.find_best_monotonic(recs, targets, top_n=1, difficulty=t.get('diff', 'hard'))

        if result:
            q, gs, best = result[0]
            for i, (r, trg) in enumerate(zip(best, targets)):
                diff_wr = r['wr'] - trg
                arrow = '↑' if diff_wr >= 0 else '↓'
                dp = r.get('deathProfile')
                death_str = ''
                if dp:
                    death_str = f'初{dp["early"]*100:.0f}% 过{dp["transition"]*100:.0f}% 中{dp["mid"]*100:.0f}% 后{dp["late"]*100:.0f}%'

                tag = f'T{i+1}'
                sd = str(r.get('sd', ''))
                ratios = str(r.get('ratios', ''))
                of_val = str(r.get('of', ''))
                src = str(r.get('source', ''))
                gap_str = '/'.join(f'{g:.0f}' for g in gs)

                print(f'  {lv:>3} {status:>8} {tag:>4} {r["wr"]:>5.1f}%{arrow}{abs(diff_wr):>+5.1f} {sd:>4} {ratios:<18} {of_val:>6} {src:>6} {death_str:<20} {gap_str:<18}')
        else:
            print(f'  {lv:>3} {status:>8}  — 无组合')
            for i in range(5):
                tag = f'T{i+1}'
                print(f'  {"":>4} {"":>8} {tag:>4} {"无数据":>12}')
    print(f'\n共 {len(all_levels)} 关')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='全局状态快照')
    ap.add_argument('--levels', help='关卡过滤')
    ap.add_argument('--pending', action='store_true', help='只看待调优')
    args = ap.parse_args()

    level_filter = None
    if args.levels:
        level_filter = set()
        for part in args.levels.replace(',', ' ').split():
            if '-' in part:
                a, b = part.split('-')
                level_filter.update(range(int(a), int(b) + 1))
            else:
                level_filter.add(int(part))

    mode = 'pending' if args.pending else 'all'
    main(level_filter, mode)
