"""把 14 关入库记录（asset 配置 + 池子匹配 WR）追加到 hermes 版 手动挑配置记录.xlsx"""
import sys, openpyxl
sys.path.insert(0, r'D:\download\BlastGame\hermes')
from tools.asset_patcher import read_ddc
from tools.data.pool import get_all_records, dedup_records

XL = r'D:\download\BlastGame\hermes\手动挑配置记录.xlsx'

def norm_ratios(r):
    return str(r or '').strip().replace('，', ',').split(',')

# 这 14 关是我们入库过的（asset 配置为入库配置）
LEVELS = ['153', '155', '158', '159', '163', '168', '172', '174', '175', '184', '186', '187', '194', '197', '199']

# L155/L187 的 T1/T2 用多档位 summary 值（池子 dedup 被 phase0 覆盖）
OVERRIDE = {
    '155': {0: 0.833, 1: 0.833},
    '187': {0: 0.848, 1: 0.848},
}

rows_to_add = []
for lv in LEVELS:
    asset = read_ddc(int(lv))
    if not asset:
        print(f'L{lv}: 无 asset')
        continue
    recs = dedup_records(get_all_records(lv))
    ver = [r for r in recs if r.get('source') in ('bot', 'summary', 'phase0')]
    # 找每档匹配
    tier_rows = []
    ok = True
    for i, cfg in enumerate(asset):
        k = (str(cfg['sd']).strip(), str(cfg['sc']).strip(), ','.join(norm_ratios(cfg['ratios'])).strip())
        match = None
        for r in ver:
            rk = (str(r.get('sd', '')).strip(), str(r.get('sc', '')).strip(), ','.join(norm_ratios(r.get('ratios'))).strip())
            if rk == k:
                try:
                    if abs(float(r.get('of', 0) or 0) - float(cfg['of'] or 0)) < 1e-6:
                        match = r
                        break
                except ValueError:
                    continue
        if lv in OVERRIDE and i in OVERRIDE[lv]:
            wr = OVERRIDE[lv][i]
            src = '多档位summary'
            games = '240/210局'
        elif match:
            wr = match['wr'] / 100
            src = match.get('source', '?')
            games = f"{match.get('totalGames', '?')}局"
        else:
            print(f'  L{lv} T{i+1}: 无匹配')
            ok = False
            break
        note = f'{src} {games} 2026-08-04'
        tier_rows.append((i + 1, wr, int(cfg['sd']), int(cfg['sc']), str(cfg['ratios']), float(cfg['of'] or 0), note))
    if not ok:
        continue
    # 组装（关卡号只在第一行）
    for idx, (tier, wr, sd, sc, ratios, of, note) in enumerate(tier_rows):
        rows_to_add.append((int(lv) if idx == 0 else None, None, tier, wr, sd, sc, ratios, of, note))
    print(f'L{lv}: {" → ".join(f"{r[1]*100:.1f}%" for r in tier_rows)}')

# 追加
wb = openpyxl.load_workbook(XL)
ws = wb.active
last = ws.max_row
for r in rows_to_add:
    last += 1
    for col, val in enumerate(r, 1):
        ws.cell(row=last, column=col, value=val)
wb.save(XL)
print(f'\n共追加 {len(rows_to_add)} 行, 现在 {ws.max_row} 行')
wb.close()
