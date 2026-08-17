"""生成 6 关（155/156/166/183/187/200）写入关卡数据库的 payload。

胜率来源：asset 当前配置（write_ddc 四元组）→ 池子 filter_verified 匹配同配置记录。
L155/L187 的 T1/T2 用多档位 summary 原始值（池子 dedup 可能埋掉）。
"""
import sys, json, os
sys.path.insert(0, r'D:\download\BlastGame\hermes')
from tools.asset_patcher import read_ddc
from tools.data.pool import get_all_records, dedup_records, filter_verified

LV = [155, 156, 166, 183, 187, 200]

# L155/L187 T1/T2 多档位 summary 原始值（池子被 phase0 覆盖）
OVERRIDE = {
    '155': {0: 0.833, 1: 0.833},
    '187': {0: 0.848, 1: 0.848},
}

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
        # 配置四元组归一化
        tc = {
            'startDifficulty': int(cfg['sd']),
            'shuffleSplitCount': int(cfg['sc']),
            'shuffleSplitRatios': str(cfg['ratios']),
            'shuffleOverflowFactor': float(cfg['of'] or 0),
        }
        tier_configs.append(tc)
        # 匹配池子同配置
        match = None
        for r in ver:
            rk = (str(r.get('sd', '')).strip(), str(r.get('sc', '')).strip(),
                  ','.join(norm_ratios(r.get('ratios'))).strip())
            ak = (str(cfg['sd']).strip(), str(cfg['sc']).strip(),
                  ','.join(norm_ratios(cfg['ratios'])).strip())
            if rk == ak and abs(float(r.get('of', 0) or 0) - float(cfg['of'] or 0)) < 1e-6:
                match = r
                break
        if str(lv) in OVERRIDE and i in OVERRIDE[str(lv)]:
            wr = OVERRIDE[str(lv)][i]
            src = 'OVERRIDE summary'
            fbd = None
        elif match:
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
        'importedAt': '2026-08-05T10:00:00.000Z',
        'sourceFileName': 'hermes-import-20260805.csv',
    }
    print(f'L{lv}: ✅ payload 生成')

out = r'D:\download\BlastGame\hermes\tools\leveldb_sync\_write_payload_20260805.json'
json.dump(payload, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'\n已保存: {out} ({len(payload)} 关)')
