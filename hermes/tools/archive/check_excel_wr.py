import csv, os, glob, openpyxl, sys

repo = os.environ.get('BLASTGAME_REPO', os.path.join(os.path.expanduser('~'), 'Documents', 'BlastGame'))
base = os.path.join(repo, 'telemetry', 'bot', '101-200-2026-07-20T17-34-01')
ext_data = {}
for tier in range(1, 6):
    files = glob.glob(os.path.join(base, f'L101-200-T{tier}-*', f'campaign-summary-L101-200-T{tier}.csv'))
    if not files: continue
    with open(files[0]) as f:
        for row in csv.DictReader(f):
            lv = row['level']
            if lv not in ext_data: ext_data[lv] = {}
            ext_data[lv][tier] = {
                'wr': float(row['winkate']) * 100,
                'sd': row['startDifficulty'],
                'sc': row['shuffleSplitCount'],
                'ratios': row['shuffleSplitRatios'].replace('"','').replace(' ',''),
                'of': str(float(row['shuffleOverflowFactor'])),
            }

excel_path = os.path.join(repo, 'Doc', '手动挑配置记录.xlsx')
wb = openpyxl.load_workbook(excel_path, data_only=True)
ws = wb.active
row_lv = {}
lv = None
for r in range(2, ws.max_row + 1):
    c = ws.cell(r, 1).value
    if c is not None: lv = str(int(c))
    row_lv[r] = lv

excel_data = {}
for r in range(2, ws.max_row + 1):
    lv = row_lv.get(r)
    if not lv or not (101 <= int(lv) <= 200): continue
    tier = str(ws.cell(r, 3).value or '').strip()
    wr_raw = ws.cell(r, 4).value
    sd = ws.cell(r, 5).value
    sc = ws.cell(r, 6).value
    ratios = ws.cell(r, 7).value
    of_val = ws.cell(r, 8).value
    if tier and wr_raw is not None and str(wr_raw).strip():
        if lv not in excel_data: excel_data[lv] = {}
        _tier_map = {'Tier1':1,'Tier2':2,'Tier3':3,'Tier4':4,'Tier5':5}
        ti = _tier_map.get(tier)
        if not ti: continue
        w = float(wr_raw)
        wr = 100.0 if w == 1.0 else (w * 100 if w < 1 else w)
        excel_data[lv][ti] = {
            'wr': wr,
            'sd': str(int(float(sd))) if sd and str(sd).strip() else '',
            'sc': str(int(float(sc))) if sc and str(sc).strip() else '',
            'ratios': str(ratios or '').replace(' ',''),
            'of': str(float(of_val)) if of_val is not None and str(of_val).strip() else '0.0',
        }

done = {'108','112','124','146','160','171'}

def norm_of(v):
    try: return f'{float(v):.3f}'.rstrip('0').rstrip('.')
    except: return str(v).strip()

_nt = {1:'T1',2:'T2',3:'T3',4:'T4',5:'T5'}

# Find 5/5 config-match levels
full_match = []
for lv in sorted(ext_data.keys(), key=int):
    if lv in done: continue
    if lv not in excel_data: continue
    all_match = True
    for ti in range(1, 6):
        ext = ext_data[lv].get(ti)
        excel = excel_data[lv].get(ti)
        if not ext or not excel:
            all_match = False
            break
        if not (excel['sd'] == ext['sd'] and 
                excel['sc'] == ext['sc'] and 
                excel['ratios'] == ext['ratios'] and
                norm_of(excel['of']) == norm_of(ext['of'])):
            all_match = False
            break
    if all_match:
        full_match.append(lv)

print(f'全5档配置一致: {len(full_match)}关')
print()

# WR diff >= 10pp
print('=== 差≥10pp（Excel需更新）===')
big = []
for lv in full_match:
    diffs = [ext_data[lv][ti]['wr'] - excel_data[lv][ti]['wr'] for ti in range(1, 6)]
    max_diff = max(abs(d) for d in diffs)
    if max_diff >= 10:
        big.append(lv)
        # Find which tiers have big diffs
        bad = [f'T{ti+1}({d:+.0f}pp)' for ti, d in enumerate(diffs) if abs(d) >= 10]
        t_str = ' '.join(f'{d:>+6.1f}' for d in diffs)
        print(f'L{lv}: {t_str}  ({", ".join(bad)})')
print(f'共 {len(big)}关')
print()

# 5-10pp
print('=== 差5-10pp ===')
mid = []
for lv in full_match:
    diffs = [ext_data[lv][ti]['wr'] - excel_data[lv][ti]['wr'] for ti in range(1, 6)]
    max_diff = max(abs(d) for d in diffs)
    if 5 <= max_diff < 10:
        mid.append(lv)
        t_str = ' '.join(f'{d:>+6.1f}' for d in diffs)
        print(f'L{lv}: {t_str}')
print(f'共 {len(mid)}关')
print()

# < 5pp
print(f'差<5pp: {len(full_match) - len(big) - len(mid)}关')