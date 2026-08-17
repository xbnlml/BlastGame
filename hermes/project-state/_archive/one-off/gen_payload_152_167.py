"""生成 2 关（152/167）写入关卡数据库的 payload（2026-08-05）。

胜率来源：asset 当前配置（write_ddc 四元组）→ 池子 filter_verified 匹配同配置记录。
与 gen_payload_6lv.py 同一逻辑。
"""
import sys, json
sys.path.insert(0, r'D:\download\BlastGame\hermes')
from tools.asset_patcher import read_ddc
from tools.data.pool import get_all_records, dedup_records, filter_verified

LV = [152, 167]

def norm_ratios(r):
    return str(r or '').strip().replace('，', ',').split(',')

payload = {}
for lv in LV:
    asset = read_ddc(lv)
    if not asset:
        print(f'L{lv}: 无 asset!')
        continue
    recs = dedup_records(get_all_records(str(lv)))
    ver = filter_verified(recs)
    tier_configs = []
    tier_wrs = []
    tier_fbd = []
    ok = True
    for i, cfg in enumerate(asset):
        tc = {
            'startDifficulty': int(cfg['sd']),
            'shuffleSplitCount': int(cfg['sc']),
            'shuffleSplitRatios': str(cfg['ratios']),
            'shuffleOverflowFactor': float(cfg['of'] or 0),
        }
        tier_configs.append(tc)
        match = None
        for r in ver:
            rk = (str(r.get('sd', '')).strip(), str(r.get('sc', '')).strip(),
                  ','.join(norm_ratios(r.get('ratios'))).strip())
            ak = (str(cfg['sd']).strip(), str(cfg['sc']).strip(),
                  ','.join(norm_ratios(cfg['ratios'])).strip())
            if rk == ak and abs(float(r.get('of', 0) or 0) - float(cfg['of'] or 0)) < 1e-6:
                match = r
                break
        if match:
            wr = match['wr'] / 100
            src = f"{match.get('source')} {match.get('totalGames')}局"
            fbd = match.get('failBucketDistribution')
        else:
            print(f'  L{lv} T{i+1}: 池子无匹配!')
            ok = False
            break
        tier_wrs.append(round(wr, 4))
        tier_fbd.append(fbd)
        print(f'  L{lv} T{i+1}: WR={wr*100:.2f}% ({src})')
    if not ok:
        print(f'L{lv}: 跳过（池子缺数据）')
        continue
    payload[str(lv)] = {
        'tierConfigs': tier_configs,
        'tierWinRates': tier_wrs,
        'tierFailDistribution': tier_fbd,
        'importedAt': '2026-08-05T15:10:00.000Z',
        'sourceFileName': 'hermes-import-20260805b.csv',
    }
    print(f'L{lv}: ✅ payload 生成')

out = r'D:\download\BlastGame\hermes\tools\leveldb_sync\_write_payload_152_167.json'
json.dump(payload, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'\n已保存: {out} ({len(payload)} 关)')
