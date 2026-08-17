#!/usr/bin/env python3
"""① 重选最优档位 + 对比 Excel 入库记录（只读，不写任何文件）。

用法：
  python tools/compare_imported.py                     # 全部已入库关
  python tools/compare_imported.py --levels 158,174    # 指定关
  python tools/compare_imported.py --levels 151-200    # 区间
  python tools/compare_imported.py --threshold 2       # 变化阈值（默认 2pp，展示用）
  python tools/compare_imported.py --json              # JSON 输出
  # 分类（坑 117）：判定变好(不合格/接近→合格)且变化>2pp = 应更新；判定不变仅变化>5pp 提示

输出：每关 Excel 入库值 vs 池子重选值 + 判定变化 + 最大档差 + 重选组合来源/局数。
纯只读：不写 _rounds.json、不改任何文件（查询绝不调 judge_with_rounds，坑 43）。
"""
import argparse
import json
import os
import re
import sys

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

from tools.data.adapters import excel_target as et
from tools.data.pool import get_all_records, dedup_records, filter_verified, find_best_monotonic
from tools.judge_level import check_judgment

XL_PATH = os.path.join(HERMES, '手动挑配置记录.xlsx')
BOARD_PATH = os.path.join(HERMES, 'project-state', 'board.md')


def parse_levels(s):
    """'151,157' / '151-200' / 空(全部已入库) → sorted list"""
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
    """board ✅已入库 的关卡列表（坑 99：board 是状态真源）"""
    if not os.path.exists(BOARD_PATH):
        return []
    lvs = []
    for line in open(BOARD_PATH, encoding='utf-8'):
        m = re.match(r'\|\s*(\d+)\s*\|\s*(\w+)\s*\|\s*(✅已入库)\s*\|', line)
        if m:
            lvs.append(int(m.group(1)))
    return sorted(lvs)


def read_excel():
    """读 Excel 入库记录：{lv: {tier: wr小数}}（只读模式）"""
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
            if row[3] is not None:
                excel.setdefault(cur, {})[tier] = row[3]
    wb.close()
    return excel


def compare_level(lv, excel, threshold=2.0):
    """单关对比。返回 dict 或 None（无数据/无记录时）。"""
    t = et.get_target(lv)
    if not t:
        return None
    recs = dedup_records(get_all_records(str(lv)))
    ver = filter_verified(recs)  # 铁则：只用 bot/summary/phase0（坑 2）
    res = find_best_monotonic(ver, t['tiers'], top_n=1, difficulty=t['diff'])
    if not res or not res[0]:
        return {'lv': lv, 'status': 'no_combo', 'diff': t['diff'], 'targets': t['tiers']}
    best = res[0][2]
    new_wrs = [r['wr'] for r in best]
    # A3（2026-08-05 审查）：Excel 单位防御——当前数据全是小数（坑 115，
    # 0.8=80%），而 new_wrs 是池子百分数（90.7）。对比必须统一到百分数。
    # 历史出过百分数事故（坑 107），防御：Excel 值 ≤2 视为小数转百分数(×100)，
    # >2 视为已是百分数保持不变；字符串强转 float。
    old_wrs = None
    if lv in excel and len(excel[lv]) >= 5:
        old_wrs = []
        for i in range(1, 6):
            v = excel[lv][i]
            try:
                v = float(v)
            except (TypeError, ValueError):
                old_wrs = None
                break
            if abs(v) <= 2:
                v *= 100.0  # 小数(0.8=80%) → 百分数(80.0)
            old_wrs.append(v)

    result = {
        'lv': lv,
        'status': 'ok',
        'diff': t['diff'],
        'targets': t['tiers'],
        'new_wrs': [round(w, 2) for w in new_wrs],
        'new_sources': [{'source': r.get('source'), 'games': r.get('totalGames'),
                         'created_at': str(r.get('created_at', ''))[:16]} for r in best],
        'old_wrs': [round(w, 2) for w in old_wrs] if old_wrs else None,
    }
    if old_wrs:
        result['max_diff'] = round(max(abs(new_wrs[i] - old_wrs[i]) for i in range(5)), 2)
        result['verdict_old'] = check_judgment(
            {f'T{i+1}': old_wrs[i] for i in range(5)}, t['diff'], t['tiers'])[0]
        result['verdict_new'] = check_judgment(
            {f'T{i+1}': new_wrs[i] for i in range(5)}, t['diff'], t['tiers'])[0]
    else:
        # A1（2026-08-05 审查）：Excel 无/缺记录必须显式标记，不能静默归"无变化"
        result['status'] = 'excel_partial' if (lv in excel and len(excel[lv]) < 5) else 'excel_missing'
    return result


def main():
    ap = argparse.ArgumentParser(description='重选最优档位 vs Excel 入库记录对比（只读）')
    ap.add_argument('--levels', help='关卡列表/区间，默认全部已入库')
    ap.add_argument('--threshold', type=float, default=2.0, help='变化阈值 pp（默认 2）')
    ap.add_argument('--json', action='store_true', help='JSON 输出')
    ap.add_argument('--all', action='store_true', help='显示全部（含无变化）')
    args = ap.parse_args()

    if args.levels:
        lvs = parse_levels(args.levels)
    else:
        lvs = get_imported_levels()

    excel = read_excel()
    results = []
    for lv in lvs:
        r = compare_level(lv, excel, args.threshold)
        if r:
            results.append(r)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return

    # 文本输出
    print(f'已入库关: {len(lvs)} 个，有数据: {len(results)} 个')
    print()

    # A2（2026-08-05 审查，坑 117 定稿规则）：分类以判定变化优先——
    # 判定变好（不合格/接近→合格）且 max_diff>2 = 应更新；判定不变仅 max_diff>5 提示。
    # 默认阈值 2pp 只是展示阈值，判定变化是主标准。
    improved = [r for r in results if r.get('status') == 'ok' and r.get('verdict_old') and r.get('verdict_new')
                and r['verdict_old'] != '合格' and r['verdict_new'] == '合格'
                and r.get('max_diff', 0) > args.threshold]
    changed = [r for r in results if r.get('status') == 'ok' and r.get('old_wrs')
               and r.get('max_diff', 0) > args.threshold and r not in improved]
    no_change = [r for r in results if r.get('status') == 'ok' and (not r.get('old_wrs')
                 or r.get('max_diff', 0) <= args.threshold)]
    no_combo = [r for r in results if r.get('status') == 'no_combo']
    excel_missing = [r for r in results if r.get('status') in ('excel_missing', 'excel_partial')]

    for r in improved:
        print(f'🔴 L{r["lv"]} [{r["diff"]}] 判定变好: {r.get("verdict_old")}→{r.get("verdict_new")} (变化{r["max_diff"]:.1f}pp) — 应更新')
        print(f'  Excel: ' + ' / '.join(f'{w:.1f}' for w in r['old_wrs']))
        print(f'  重选:  ' + ' / '.join(f'{w:.1f}' for w in r['new_wrs']))
        for i, s in enumerate(r['new_sources']):
            print(f'    T{i+1}: {s["source"]} {s["games"]}局 {s["created_at"]}')
    for r in changed:
        print(f'🟡 L{r["lv"]} [{r["diff"]}] 变化{r["max_diff"]:.1f}pp | 判定 {r.get("verdict_old")}→{r.get("verdict_new")}')
        print(f'  Excel: ' + ' / '.join(f'{w:.1f}' for w in r['old_wrs']))
        print(f'  重选:  ' + ' / '.join(f'{w:.1f}' for w in r['new_wrs']))
    print()
    if excel_missing:
        print(f'⚠️ Excel 无/缺记录: {[(r["lv"], r["status"]) for r in excel_missing]}')
    if no_combo:
        print(f'无组合: {[r["lv"] for r in no_combo]}')
    if args.all:
        print(f'无变化（≤{args.threshold}pp）: {[r["lv"] for r in no_change]}')
    print(f'应更新(判定变好): {len(improved)} 关 | 其他变化: {len(changed)} 关')


if __name__ == '__main__':
    main()
