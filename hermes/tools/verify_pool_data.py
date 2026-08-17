#!/usr/bin/env python3
"""③ 数据可靠性核验（只读）：池子数据是否全部有效。

三查（对应 2026-08-05 用户问的"池子里都是有效数据吗"）：
  1. 来源合规：池子原始数据可含 phase1/2（参考），但 filter_verified 后必须只剩 bot/summary/phase0
  2. filter_verified 过滤：报告过滤前后条数
  3. dedup 去重：同配置多条时是否取 pool 规则应保留的那条（坑 87：of 必须 float 归一化，
     同键用 pool._config_key；来源优先级：bot/summary/phase0 同级取 created_at 最新，
     phase1/2 受罚永不压过 verified——2026-08-05 审查 B1/B2 修复）
  4. wr=0 占位垃圾检测（坑：source=summary + games=0 + wr=0 能过 filter_verified，必须剔除）

用法：
  python tools/verify_pool_data.py                  # 全部已入库关
  python tools/verify_pool_data.py --levels 158,174
  python tools/verify_pool_data.py --levels 151-200
"""
import argparse
import os
import re
import sys
from collections import defaultdict

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

from tools.data.pool import get_all_records, dedup_records, filter_verified, _config_key, _source_penalty

BOARD_PATH = os.path.join(HERMES, 'project-state', 'board.md')


def parse_levels(s):
    out = set()
    for part in str(s or '').split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-')
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out)


def get_imported_levels():
    if not os.path.exists(BOARD_PATH):
        return []
    lvs = []
    for line in open(BOARD_PATH, encoding='utf-8-sig'):
        m = re.match(r'\|\s*(\d+)\s*\|\s*(\w+)\s*\|\s*(✅已入库)\s*\|', line)
        if m:
            lvs.append(int(m.group(1)))
    return sorted(lvs)


def pool_should_win(records):
    """复刻 pool.dedup_records 的取舍：同级(penalty 相同)取 created_at 新；phase1/2 受罚永不压过 verified。
    返回应保留的记录（多条同 penalty 时取最新）。
    """
    best = None
    best_pen = None
    for r in records:
        pen = _source_penalty(r.get('source', ''), r.get('totalGames', 0))
        if best is None or pen < best_pen or (pen == best_pen and r.get('created_at', '') > best.get('created_at', '')):
            best = r
            best_pen = pen
    return best


def verify_level(lv):
    """返回 (ok, issues[], info)"""
    issues = []
    recs = get_all_records(str(lv))
    if not recs:
        return True, [], {'total': 0}

    # 1. filter_verified 后来源合规
    ver = filter_verified(recs)
    ver_srcs = defaultdict(int)
    for r in ver:
        ver_srcs[str(r.get('source', ''))] += 1
    bad_ver = {k: v for k, v in ver_srcs.items() if k not in ('bot', 'summary', 'phase0')}
    if bad_ver:
        issues.append(f'filter_verified 后仍有 {bad_ver}')

    # 2. wr=0 占位垃圾（坑：summary+games=0+wr=0 能过 filter_verified）
    garbage = [r for r in ver if r.get('wr', 0) <= 0]
    if garbage:
        issues.append(f'{len(garbage)} 条 wr<=0 占位垃圾（应剔除）')

    # 3. dedup 是否按 pool 规则保留正确记录（B1：of 归一用 pool._config_key；B2：来源优先级）
    deduped = dedup_records(recs)
    dedup_by_key = {}
    for d in deduped:
        dedup_by_key[_config_key(d)] = d

    groups = defaultdict(list)
    for r in recs:
        groups[_config_key(r)].append(r)

    stale = 0
    for key, grp in groups.items():
        if len(grp) > 1:
            should_win = pool_should_win(grp)
            kept = dedup_by_key.get(key)
            if kept is None or kept.get('created_at', '') != should_win.get('created_at', '') \
                    or kept.get('wr') != should_win.get('wr'):
                stale += 1
                issues.append(f'配置 {key}: dedup 保留与 pool 规则不符')

    info = {
        'total': len(recs),
        'verified': len(ver),
        'garbage': len(garbage),
        'verified_sources': dict(ver_srcs),
        'stale': stale,
    }
    return (len(issues) == 0), issues, info


def main():
    ap = argparse.ArgumentParser(description='池子数据可靠性核验（只读）')
    ap.add_argument('--levels', help='关卡列表/区间，默认全部已入库')
    args = ap.parse_args()

    lvs = parse_levels(args.levels) if args.levels else get_imported_levels()

    print(f'核验 {len(lvs)} 关池子数据')
    print()
    all_ok = True
    for lv in lvs:
        ok, issues, info = verify_level(lv)
        if info.get('total', 0) == 0:
            print(f'L{lv}: 池子为空')
            continue
        flag = '✅' if ok else '❌'
        if not ok:
            all_ok = False
        g_str = f' 垃圾={info["garbage"]}' if info.get('garbage') else ''
        print(f'{flag} L{lv}: 共{info["total"]}条 → verified {info["verified"]}条{g_str} | 来源={info["verified_sources"]}')
        for iss in issues:
            print(f'    ⚠️ {iss}')
    print()
    print('✅ 全部合规' if all_ok else '❌ 有不合规项（见上）')


if __name__ == '__main__':
    main()
