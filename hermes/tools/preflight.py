#!/usr/bin/env python3
"""提交前验证 — 防越界、防漏检、防低级错误。

用法:
  python tools/preflight.py submit --levels 59,81,82 --tiers 1,2,3,4,5
  python tools/preflight.py asset --levels 59,81,82
"""
import os, sys, json, subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

REPO = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))

def get_asset_path(lv):
    for root, dirs, files in os.walk(os.path.join(REPO, 'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test')):
        if f'{lv}.asset' in files:
            return os.path.join(root, f'{lv}.asset')
    return os.path.join(REPO, 'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test', f'{lv}.asset')

def get_board_levels():
    """读取 board.md 的入库/改关卡列表"""
    bp = os.path.join(TOOL_DIR, '..', 'project-state', 'board.md')
    if not os.path.exists(bp): return set(), set(), set()
    done, retired, pending = set(), set(), set()
    section = None
    with open(bp, encoding='utf-8') as f:
        for line in f:
            if '入库' in line: section = 'done'
            elif '改关卡' in line: section = 'retired'
            elif '空白' in line or '待选' in line or '待调优' in line: section = 'pending'
            if section and '---' not in line:
                for w in line.replace(',', ' ').split():
                    try:
                        lv = int(w)
                        if 51 <= lv <= 200:
                            if section == 'done': done.add(lv)
                            elif section == 'retired': retired.add(lv)
                            elif section == 'pending': pending.add(lv)
                    except: pass
    return done, retired, pending


def check_asset_integrity(levels):
    """检查 asset 是否纯净 5 档"""
    errors = []
    for lv in levels:
        fp = get_asset_path(lv)
        if not os.path.exists(fp):
            errors.append('L{}: asset 文件不存在'.format(lv))
            continue
        from tools.asset_patcher import read_ddc as rd
        cfg = rd(lv)
        if not cfg:
            errors.append('L{}: asset 读不出'.format(lv))
        elif len(cfg) < 5:
            errors.append('L{}: asset 仅 {} 档（应 5）'.format(lv, len(cfg)))
        elif len(cfg) > 5:
            errors.append('L{}: asset 有 {} 档重复配置（应 5，>5 会导致 batch mode 空 CSV）'.format(lv, len(cfg)))
        else:
            for i, c in enumerate(cfg):
                n_vals = len(str(c.get('ratios', '')).split(','))
                sc = int(c.get('sc', 0))
                if n_vals != sc:
                    errors.append('L{} T{}: ratios 值数({}) != sc({})'.format(lv, i+1, n_vals, sc))
    return errors


def check_asset_readback(levels):
    """读 asset 对比 probe_configs — 检测写入与实际存储是否一致。
    只输出信息，不阻止提交（首次写入新配置时不匹配是正常的）。"""
    warnings = []
    with open(os.path.join(TOOL_DIR, 'probe_configs.json')) as f:
        cfg = json.load(f)
    for lv in levels:
        slv = str(lv)
        if slv not in cfg:
            continue
        from tools.asset_patcher import read_ddc
        cur = read_ddc(lv)
        if not cur:
            warnings.append(f'  L{lv}: asset 读不出（可能是首次）')
            continue
        expected = []
        for i in range(1, 6):
            key = f'T{i}'
            t = cfg[slv].get(key)
            if not t:
                expected.append({'sd': 0, 'sc': 5, 'ratios': '1,1,1,1,1', 'of': 0.5})
            else:
                expected.append(t)
        mismatches = 0
        for i in range(5):
            e, a = expected[i], cur[i]
            for field in ('sd', 'sc', 'ratios', 'of'):
                if str(e.get(field)) != str(a.get(field)):
                    mismatches += 1
        if mismatches > 0:
            warnings.append(f'  L{lv}: asset 与 probe_configs 不一致（{mismatches}处，首次提交正常）')
    return warnings  # 不改 errors，只警告


def check_probe_configs(levels):
    """检查 probe_configs 完整性"""
    errors = []
    with open(os.path.join(TOOL_DIR, 'probe_configs.json')) as f:
        cfg = json.load(f)
    for lv in levels:
        slv = str(lv)
        if slv not in cfg:
            errors.append('L{}: probe_configs 中无此关卡'.format(lv))
            continue
        for i in range(1, 6):
            key = 'T{}'.format(i)
            t = cfg[slv].get(key)
            if not t:
                errors.append('L{} {}: 缺失'.format(lv, key))
                continue
            n_vals = len(str(t.get('ratios', '')).split(','))
            sc = int(t.get('sc', 0))
            if n_vals != sc:
                errors.append('L{} {}: ratios 值数({}) != sc({})'.format(lv, key, n_vals, sc))
            sd = t.get('sd', -1)
            ofv = t.get('of', -1)
            if not (0 <= sd <= 50):
                errors.append('L{} {}: sd={} 超出 0-50'.format(lv, key, sd))
            if not (0 <= ofv <= 1):
                errors.append('L{} {}: of={} 超出 0-1'.format(lv, key, ofv))
    return errors
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='提交前验证')
    sp = ap.add_subparsers(dest='cmd', required=True)
    
    p = sp.add_parser('submit', help='验证提交')
    p.add_argument('--levels', required=True)
    p.add_argument('--tiers', default='')
    p.add_argument('--unit-only', action='store_true', help='只验证 asset，不涉及 Unity')
    
    p2 = sp.add_parser('asset', help='只验证 asset 完整性')
    p2.add_argument('--levels', required=True)
    
    p3 = sp.add_parser('check-retired', help='检查改关卡关是否有新组合，有则移回待调优')
    p3.add_argument('--dry-run', action='store_true', help='只展示不修改')

    args = ap.parse_args()
    
    levels = []
    if args.cmd in ('submit', 'asset'):
        for part in args.levels.replace(',', ' ').split():
            part = part.strip()
            if '-' in part:
                a, b = part.split('-')
                levels.extend(range(int(a), int(b)+1))
            else:
                levels.append(int(part))
    
    has_error = False
    
    if args.cmd == 'submit':
        # 1. --tiers 非空
        if not args.tiers:
            print('❌ --tiers 未设置')
            has_error = True
        
        # 2. asset 5 档
        errs = check_asset_integrity(levels)
        for e in errs:
            print('❌ ' + e)
            has_error = True
        if not errs:
            print('✅ asset 5 档完整')
        
        # 3. probe_configs 完整性
        errs = check_probe_configs(levels)
        for e in errs:
            print('❌ ' + e)
            has_error = True
        if not errs:
            print('✅ probe_configs 完整')
        
        # 3.5. asset 回读对比 probe_configs（仅信息，不阻止提交）
        if not args.unit_only and not has_error:
            warnings = check_asset_readback(levels)
            for w in warnings:
                print('ℹ️ ' + w)
            if not warnings:
                print('✅ asset 当前配置与 probe_configs 一致' if not has_error else '')
        
        # 4. board 已入库检查
        if not args.unit_only:
            done, retired, _ = get_board_levels()
            already_done = [lv for lv in levels if lv in done]
            already_retired = [lv for lv in levels if lv in retired]
            if already_done:
                print('⚠️ 以下关卡已入库，一般不重跑: {}'.format(','.join(str(x) for x in already_done)))
            if already_retired:
                print('⚠️ 以下关卡已改关卡，注意验证数据有效性: {}'.format(','.join(str(x) for x in already_retired)))
        
        # 5. Unity 冲突检查
        if not args.unit_only:
            try:
                r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Unity.exe', '/NH'],
                                 capture_output=True, text=True, encoding='gbk', errors='replace')
                if 'Unity.exe' in (r.stdout or ''):
                    print('⚠️ Unity 编辑器进程存在，batch mode 可能 license 冲突')
            except Exception:
                pass
        
        # 6. 数据源预览（防只看一种来源）
        print()
        print('📊 数据源预览:')
        from tools.data import pool as pool2
        for lv in levels:
            recs = pool2.dedup_records(pool2.get_preferred_records(str(lv)))
            n_bot = sum(1 for r in recs if r.get('source')=='bot' and r.get('totalGames',0)>=400)
            n_sum = sum(1 for r in recs if r.get('source')=='summary' and r.get('totalGames',0)>=400)
            n_p2 = sum(1 for r in recs if r.get('source') in ('phase2','phase1'))
            wrs = [r['wr']*100 for r in recs if r.get('source') in ('bot','summary') and r.get('totalGames',0)>=400]
            wr_range = '{:.0f}-{:.0f}%'.format(min(wrs),max(wrs)) if wrs else '无可靠'
            print('  L{}: bot400={} sum400={} phase={} WR范围={}'.format(lv,n_bot,n_sum,n_p2,wr_range))
        
        if has_error:
            print('❌ 验证未通过')
            sys.exit(1)
        else:
            print('✅ 全部通过')
    
    elif args.cmd == 'asset':
        errs = check_asset_integrity(levels)
        for e in errs:
            print('❌ ' + e)
            has_error = True
        if not errs:
            print('✅ 全部 {} 关 asset 完整'.format(len(levels)))
        
        sys.exit(1 if has_error else 0)
    
    elif args.cmd == 'check-retired':
        from tools.data import pool
        from tools.data.adapters import excel_target as et
        
        done, retired, pending = get_board_levels()
        restored = []
        for lv in sorted(retired):
            t = et.get_target(lv)
            if not t: continue
            recs = pool.dedup_records(pool.get_preferred_records(str(lv)))
            r = pool.find_best_monotonic(recs, t['tiers'], top_n=1, difficulty=t['diff'])
            if r:
                _,gs,rs=r[0]
                wrs=[x['wr']*100 for x in rs]
                gs_str='/'.join('{:.0f}'.format(g) for g in gs)
                print('L{}: ✅ 有组合 {:.0f}/{:.0f}/{:.0f}/{:.0f}/{:.0f} gaps={}'.format(
                    lv,wrs[0],wrs[1],wrs[2],wrs[3],wrs[4],gs_str))
                if not args.dry_run:
                    restored.append(lv)
            else:
                print('L{}: ❌ 无组合'.format(lv))
        
        if restored:
            # Update board.md
            bp = os.path.join(TOOL_DIR, '..', 'project-state', 'board.md')
            with open(bp, 'r', encoding='utf-8') as f:
                board = f.read()
            # Simple replace: move from retired section to pending section
            import re as re2
            for lv in restored:
                slv = str(lv)
                # Remove from retired section
                board = re2.sub(r'\b' + slv + r'\b', '', board)
                # Add to pending section
                if '待调优' in board:
                    board = board.replace('待调优 —', '待调优 — ' + slv + ',')
                elif '空白' in board:
                    board = board.replace('空白 —', '空白 — ' + slv + ',')
            # Clean up empty placeholders
            board = re2.sub(r',\s*,', ',', board)
            board = re2.sub(r',\s*\n', '\n', board)
            with open(bp, 'w', encoding='utf-8') as f:
                f.write(board)
            print('已移回待调优: {}'.format(','.join(str(x) for x in restored)))
        elif args.dry_run:
            print('(dry-run, 未修改)')
