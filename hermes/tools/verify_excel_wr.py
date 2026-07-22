#!/usr/bin/env python3
"""验证 Excel WR vs stage-data（bot 实际）WR 是否对得上"""
import json, openpyxl, glob, re, os, sys

EXCEL = r"C:\Users\Administrator\Documents\BlastGame\Doc\手动挑配置记录.xlsx"
STAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stage-data')
LEVELS_51_100 = [str(lv) for lv in range(51, 101)]


def main():
    # 读取 Excel —— 按 (lv, sd, sc, ratios, of) 索引
    wb = openpyxl.load_workbook(EXCEL)
    ws = wb.active

    prev_lv = None
    excel_map = {}  # {(lv, sd, sc, ratios, of): (tier, wr, note)}
    for r in range(2, ws.max_row + 1):
        lv_raw = ws.cell(r, 1).value
        if lv_raw:
            prev_lv = str(int(str(lv_raw)))
        lv = prev_lv
        if not lv or lv not in LEVELS_51_100:
            continue
        tier = str(ws.cell(r, 3).value or '').strip()
        wr = str(ws.cell(r, 4).value or '').strip()
        sd = str(ws.cell(r, 5).value or '').strip()
        sc = str(ws.cell(r, 6).value or '').strip()
        ratios = str(ws.cell(r, 7).value or '').strip()
        of_val = str(ws.cell(r, 8).value or '').strip()
        note = str(ws.cell(r, 9).value or '').strip()
        if sd and sd.isdigit() and wr:
            key = (lv, sd, sc, ratios, of_val)
            excel_map[key] = (tier, wr, note)

    print("=" * 80)
    print("Excel WR vs Bot 实际 WR 比对")
    print("=" * 80)

    matched = 0
    mismatched = 0
    missing = 0
    total = len(excel_map)
    results = []

    for (lv, sd, sc, ratios, of_val), (tier, wr_excel, note) in sorted(excel_map.items(), key=lambda x: (int(x[0][0]), x[1][0])):
        # 读 stage-data
        fp = os.path.join(STAGE, lv, f'{lv}.json')
        if not os.path.isfile(fp):
            print(f"  !! L{lv} {fp} 不存在")
            missing += 1
            continue
        with open(fp, encoding='utf-8') as f:
            pool = json.load(f)
        reliable = pool.get('reliable', [])

        # 在可靠池里找匹配的 (sd, sc, ratios, of)
        found = None
        for cfg in reliable:
            if (str(cfg.get('sd', '')) == sd
                and str(cfg.get('sc', '')) == sc
                and str(cfg.get('ratios', '')) == ratios
                and str(cfg.get('of', '')) == of_val):
                found = cfg
                break

        if found is None:
            # 也查参考池
            ref = pool.get('reference', [])
            for cfg in ref:
                if (str(cfg.get('sd', '')) == sd
                    and str(cfg.get('sc', '')) == sc
                    and str(cfg.get('ratios', '')) == ratios
                    and str(cfg.get('of', '')) == of_val):
                    found = cfg
                    break

        err_msg = ''
        if found is None:
            err_msg = '!! 池中无此配置'
            missing += 1
        else:
            wr_bot = float(found.get('wr', 0))  # pool wr 已经是百分数
            wr_excel_f = float(wr_excel) * 100  # Excel wr 是小数 (0.972→97.2%)
            diff = abs(wr_bot - wr_excel_f)
            if diff <= 2.0:
                matched += 1
                err_msg = f'✓ 偏差={diff:.1f}pp'
            else:
                mismatched += 1
                err_msg = f'✗ 偏差={diff:.1f}pp (Excel={wr_excel_f:.1f}% Bot={wr_bot:.1f}%)'

        results.append((lv, tier, err_msg, found))

    # 输出汇总
    print(f"\n共 {total} 条配置: 匹配 {matched}, 偏差 {mismatched}, 缺失 {missing}")
    print()

    # 按关输出
    lv_matched = {}
    lv_total = {}
    for lv, tier, msg, found in results:
        lv_matched.setdefault(lv, 0)
        lv_total.setdefault(lv, 0)
        lv_total[lv] += 1
        if msg.startswith('✓'):
            lv_matched[lv] += 1

    print(f"{'关':>4s} {'匹配数':>6s}/总数  {'档位偏差':>12s}")
    print("-" * 30)
    for lv in sorted(set(r[0] for r in results), key=int):
        n = lv_total[lv]
        m = lv_matched[lv]
        flag = '✅' if m == n else '⚠️'
        if m == 0:
            flag = '❌'
        print(f" {lv:>3s} {flag}  {m:>3d}/{n}")

    print()
    print("--- 详细偏差 ---")
    for lv, tier, msg, found in results:
        if msg.startswith('✗') or msg.startswith('!!'):
            print(f"  L{lv:>3s} {tier}: {msg}")


if __name__ == '__main__':
    main()
