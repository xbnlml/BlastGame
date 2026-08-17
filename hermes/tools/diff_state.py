#!/usr/bin/env python3
"""diff_state.py — 一键检查 asset vs Excel vs pool 是否一致。
用法: python tools/diff_state.py [关卡号]
       python tools/diff_state.py 51-100   # 范围
       python tools/diff_state.py --all    # 全部
"""
import sys, os, json

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TOOL_DIR))

from tools.asset_patcher import read_ddc
import openpyxl

# --- Paths ---
XL_PATH = os.path.join(os.path.dirname(TOOL_DIR), '手动挑配置记录.xlsx')
STAGE_DIR = os.path.join(os.path.dirname(TOOL_DIR), 'stage-data')


def parse_levels(arg):
    """Parse level spec: '82', '51,52,53', '51-100', or '--all'."""
    if arg == '--all':
        return list(range(51, 201))
    levels = []
    for part in arg.split(','):
        part = part.strip()
        if '-' in part:
            lo, hi = part.split('-')
            levels.extend(range(int(lo), int(hi) + 1))
        else:
            levels.append(int(part))
    return levels


def load_excel():
    """Return {lv: {T1: {sd, ratios, of}, ...}} from Excel."""
    wb = openpyxl.load_workbook(XL_PATH, data_only=True)
    ws = wb.active
    data = {}
    for row in ws.iter_rows(min_row=1, values_only=True):
        lv = row[0]
        if lv is None or not str(lv).isdigit():
            continue
        lv = int(lv)
        tier = str(row[2] or '').replace('Tier', 'T')
        sd = str(row[4]) if row[4] is not None else None
        ratios = str(row[6]) if row[6] is not None else None
        of_val = str(row[7]) if row[7] is not None else None
        if lv not in data:
            data[lv] = {}
        if tier:
            data[lv][tier] = {'sd': sd, 'ratios': ratios, 'of': of_val}
    return data


def load_pool(lv):
    """Return pool best records {T1: {wr, sd, ...}, ...} for one level."""
    key = str(lv)
    fp = os.path.join(STAGE_DIR, key, f'{key}.json')
    if not os.path.isfile(fp):
        return {}
    with open(fp, encoding='utf-8') as f:
        pool = json.load(f)
    reliable = pool.get('reliable', [])
    # Group by tier, take highest WR per tier
    best = {}
    for r in reliable:
        tier = str(r.get('source_tier', r.get('tier', '')))
        wr = r.get('wr', 0)
        if tier not in best or wr > best[tier][0]:
            best[tier] = (wr, r.get('sd', ''), r.get('ratios', ''),
                          r.get('of', ''), r.get('totalGames', 0))
    return best


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/diff_state.py <关卡号|范围|--all>")
        sys.exit(1)

    levels = parse_levels(sys.argv[1])
    excel = load_excel()
    issues = []

    for lv in levels:
        lv_issues = []

        # 1. Read asset
        try:
            asset_cfg = read_ddc(lv)
            if not asset_cfg:
                lv_issues.append('asset 读取失败')
                continue
        except Exception:
            lv_issues.append('asset 读取异常')
            continue

        # 2. Compare asset vs Excel
        ex = excel.get(lv, {})
        for i, c in enumerate(asset_cfg):
            tier = f'T{i+1}'
            a_sd = str(c.get('sd', ''))
            a_ratios = str(c.get('ratios', '')).replace(' ', '')
            a_of = str(c.get('of', ''))
            e = ex.get(tier, {})
            e_sd = (e.get('sd') or '')
            e_ratios = (e.get('ratios') or '').replace(' ', '')

            if e_sd is None or e_sd == 'None':
                lv_issues.append(f'{tier} Excel无数据')
            elif a_sd != e_sd or a_ratios != e_ratios:
                lv_issues.append(
                    f'{tier} 不一致: asset(sd={a_sd},r={a_ratios}) ≠ excel(sd={e_sd},r={e_ratios})')

        # 3. Compare asset vs pool
        pool_best = load_pool(lv)
        for tier_name, (wr, p_sd, p_ratios, p_of, games) in pool_best.items():
            # Simple tier mapping: T1, T2, T3, ...
            if not tier_name.startswith('T'):
                continue
            idx = 0 if 'T1' in tier_name else 1 if 'T2' in tier_name else \
                  2 if 'T3' in tier_name else 3 if 'T4' in tier_name else 4
            a_sd = str(asset_cfg[idx].get('sd', ''))
            if a_sd != str(p_sd):
                # Check if there's any asset config matching the pool best
                any_match = any(
                    str(c.get('sd', '')) == str(p_sd) and
                    str(c.get('ratios', '')).replace(' ', '') == str(p_ratios).replace(' ', '')
                    for c in asset_cfg
                )
                if not any_match:
                    lv_issues.append(
                        f'asset无池子最优 {tier_name}({wr:.0f}%,sd={p_sd},x{games})')

        if lv_issues:
            issues.append((lv, lv_issues))
            print(f'L{lv:>3d} ❌ {" | ".join(lv_issues)}')
        else:
            print(f'L{lv:>3d} ✅ asset=excel=pool')

    print(f'\n总计 {len(levels)} 关，{len(issues)} 关有不一致' if issues else '\n全部一致 ✅')


if __name__ == '__main__':
    main()
