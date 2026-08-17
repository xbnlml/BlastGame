#!/usr/bin/env python3
"""⑥ 已入库关三方审计（只读）：Excel 记录 vs asset 当前配置 vs 池子同配置 WR。

分类（坑 115/116）：
  A. asset 是探针残留（与 probe_configs.json 一致但 Excel 记录不同）→ Excel 才是入库真值
  B. 配置不同（asset ≠ Excel 配置，≥2 档）→ asset 后来被改过/Excel 未同步
  C. 配置相同但胜率差异 >5pp → 池子 dedup 变化/Excel 值失效
  D. 一致 → 正常

用法：
  python tools/audit_imported.py
  python tools/audit_imported.py --levels 151-200
"""
import argparse
import json
import os
import re
import sys

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

from tools.asset_patcher import read_ddc, config_sig
from tools.data.pool import get_all_records

XL_PATH = os.path.join(HERMES, '手动挑配置记录.xlsx')
BOARD_PATH = os.path.join(HERMES, 'project-state', 'board.md')
PROBE_PATH = os.path.join(HERMES, 'tools', 'probe_configs.json')


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
    for line in open(BOARD_PATH, encoding='utf-8'):
        m = re.match(r'\|\s*(\d+)\s*\|\s*(\w+)\s*\|\s*(✅已入库)\s*\|', line)
        if m:
            lvs.append(int(m.group(1)))
    return sorted(lvs)


def read_excel_configs():
    """读 Excel 配置：{lv: {tier: (wr小数, sd, sc, ratios, of)}}"""
    import openpyxl
    wb = openpyxl.load_workbook(XL_PATH, read_only=True)
    ws = wb.active
    excel = {}
    cur = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is not None:
            cur = int(row[0])
        if cur and row[2] and str(row[2]).startswith('Tier'):
            tier = int(str(row[2])[4:])
            excel.setdefault(cur, {})[tier] = (row[3], row[4], row[5],
                                               str(row[6] or '').replace(' ', ''), row[7])
    wb.close()
    return excel


def load_probes():
    try:
        return json.load(open(PROBE_PATH, encoding='utf-8'))
    except Exception:
        return {}


def cfg_key(cfg):
    """配置四元组归一化键。of 必须 float 转换（坑 87：str(0)='0' vs str(0.0)='0.0' 不匹配）"""
    try:
        of = f"{float(cfg.get('of', 0) or 0):.6f}"
    except (TypeError, ValueError):
        of = '0.000000'
    return (str(cfg.get('sd', '')), str(cfg.get('sc', '')),
            str(cfg.get('ratios', '')).replace(' ', ''), of)


def audit_level(lv, excel, probes):
    """返回 (category, detail)"""
    asset = read_ddc(lv)
    if not asset:
        return 'no_asset', 'asset 读取失败'

    # A. 探针残留检测：asset 与 probe_configs 一致？
    is_probe = False
    if str(lv) in probes:
        p = probes[str(lv)]
        if all(f'T{i+1}' in p for i in range(5)):
            probe_keys = [cfg_key(p[f'T{i+1}']) for i in range(5)]
            asset_keys = [cfg_key(c) for c in asset]
            if probe_keys == asset_keys:
                is_probe = True

    if lv not in excel or len(excel[lv]) < 5:
        return 'probe_residue' if is_probe else 'no_excel', \
               ('asset=探针配置，Excel 无记录' if is_probe else 'Excel 无完整 5 档')

    # 配置比对（Excel vs asset，逐档；of 走 float 归一化，坑 87）
    diff_tiers = []
    for i in range(5):
        ex = excel[lv][i + 1]
        ac = asset[i]
        ex_key = cfg_key({'sd': ex[1], 'sc': ex[2], 'ratios': ex[3], 'of': ex[4]})
        ac_key = cfg_key(ac)
        if ex_key != ac_key:
            diff_tiers.append(i + 1)

    if is_probe:
        return 'probe_residue', f'asset 是探针配置（{len(diff_tiers)} 档与 Excel 不同），Excel 才是入库真值'

    if len(diff_tiers) >= 2:
        return 'config_diff', f'{len(diff_tiers)}/5 档配置不同（asset 后来被改过/Excel 未同步）: T{diff_tiers}'

    # C. 胜率差异（配置相同的前提下，用池子同配置核对）
    recs = get_all_records(str(lv))
    wr_issues = []
    for i in range(5):
        ex = excel[lv][i + 1]
        matches = [r for r in recs if cfg_key(r) == cfg_key({
            'sd': ex[1], 'sc': ex[2], 'ratios': ex[3], 'of': ex[4]})]
        if matches:
            newest = max(matches, key=lambda r: r.get('created_at', ''))
            diff = abs(ex[0] * 100 - newest['wr'])
            if diff > 5:
                wr_issues.append(f'T{i+1}: Excel={ex[0]*100:.1f}% vs 池子最新={newest["wr"]:.1f}% (差{diff:.1f}pp)')
    if wr_issues:
        return 'wr_diff', '; '.join(wr_issues)

    return 'ok', '一致'


def main():
    ap = argparse.ArgumentParser(description='已入库关三方审计（只读）')
    ap.add_argument('--levels', help='关卡列表/区间，默认全部已入库')
    args = ap.parse_args()

    lvs = parse_levels(args.levels) if args.levels else get_imported_levels()
    excel = read_excel_configs()
    probes = load_probes()

    cats = {'probe_residue': [], 'config_diff': [], 'wr_diff': [], 'no_asset': [],
            'no_excel': [], 'ok': []}
    for lv in lvs:
        cat, detail = audit_level(lv, excel, probes)
        cats.setdefault(cat, []).append((lv, detail))

    for cat, items in cats.items():
        if not items:
            continue
        print(f'=== {cat} ({len(items)}) ===')
        for lv, detail in items:
            print(f'  L{lv}: {detail}')
        print()


if __name__ == '__main__':
    main()
