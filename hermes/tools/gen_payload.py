#!/usr/bin/env python3
"""② 生成关卡数据库写入 payload（通用版，替代手写 gen_payload_* 变体）。

胜率来源：asset 当前配置（write_ddc 四元组）→ 池子 filter_verified 匹配同配置记录。
OVERRIDE 模式：被 dedup 埋掉的用多档位 summary 原始值（坑 96/101，如 L155 T1=0.833）。

用法：
  python tools/gen_payload.py --levels 158,174 --source hermes-import-20260805c.csv
  python tools/gen_payload.py --levels 152,167 --source hermes-import-20260805b.csv \
      --override '{"155": {"0": 0.833, "1": 0.833}}' \
      --out tools/leveldb_sync/_write_payload.json
  # 注意：dryrun 硬编码读 _write_payload.json（坑 96），默认输出到那里
"""
import argparse
import json
import os
import sys

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

from tools.asset_patcher import read_ddc
from tools.data.pool import get_all_records, dedup_records, filter_verified

DEFAULT_OUT = os.path.join(HERMES, 'tools', 'leveldb_sync', '_write_payload.json')


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


def norm_ratios(r):
    return str(r or '').strip().replace('，', ',').split(',')


def gen_payload(lvs, source, override=None, imported_at=None):
    override = override or {}
    if imported_at is None:
        # 2026-08-05 审查修复：默认当前 UTC 时间（防硬编码日期过期）
        from datetime import datetime, timezone
        imported_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    payload = {}
    for lv in lvs:
        asset = read_ddc(lv)
        # 2026-08-05 审查 P0 修复：read_ddc 失败返回错误字符串（truthy），
        # `if not asset` 拦不住会逐字符迭代崩溃——必须 isinstance 检查
        if not isinstance(asset, list) or not asset:
            print(f'L{lv}: asset 读取失败!')
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
            # 先匹配池子（OVERRIDE 覆盖时打印对比，2026-08-05 审查修复）
            match = None
            for r in ver:
                rk = (str(r.get('sd', '')).strip(), str(r.get('sc', '')).strip(),
                      ','.join(norm_ratios(r.get('ratios'))).strip())
                ak = (str(cfg['sd']).strip(), str(cfg['sc']).strip(),
                      ','.join(norm_ratios(cfg['ratios'])).strip())
                if rk == ak and abs(float(r.get('of', 0) or 0) - float(cfg['of'] or 0)) < 1e-6:
                    match = r
                    break
            # OVERRIDE（防 dedup 埋掉，坑 96/101）——带结构校验 + WR 范围校验
            if str(lv) in override and isinstance(override[str(lv)], dict) and str(i) in override[str(lv)]:
                wr = float(override[str(lv)][str(i)])
                if not (0 < wr <= 1):
                    print(f'  L{lv} T{i+1}: OVERRIDE 值 {wr} 超出 (0,1]（可能误传百分数 83.3 而非 0.833）— 跳过')
                    ok = False
                    break
                if match:
                    print(f'  L{lv} T{i+1}: OVERRIDE {wr} 覆盖池子原值 {match["wr"]/100:.4f}')
                else:
                    print(f'  L{lv} T{i+1}: OVERRIDE {wr}（池子无匹配）')
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
            print(f'L{lv}: 跳过（池子缺数据或 OVERRIDE 非法）')
            continue
        payload[str(lv)] = {
            'tierConfigs': tier_configs,
            'tierWinRates': tier_wrs,
            'tierFailDistribution': tier_fbd,
            'importedAt': imported_at,
            'sourceFileName': source,
        }
        print(f'L{lv}: ✅ payload 生成')
    return payload


def main():
    ap = argparse.ArgumentParser(description='生成关卡数据库 payload（asset 配置匹配池子）')
    ap.add_argument('--levels', required=True, help='关卡列表/区间')
    ap.add_argument('--source', required=True, help='sourceFileName（如 hermes-import-20260805c.csv）')
    ap.add_argument('--override', default='{}', help='JSON: {lv: {tier_idx: wr小数}} 防 dedup 埋')
    ap.add_argument('--out', default=DEFAULT_OUT, help=f'输出路径（默认 {DEFAULT_OUT}，dryrun 读这个）')
    ap.add_argument('--imported-at', default='2026-08-05T16:00:00.000Z', help='importedAt 时间')
    args = ap.parse_args()

    lvs = parse_levels(args.levels)
    try:
        override = json.loads(args.override)
    except json.JSONDecodeError as e:
        print(f'--override JSON 解析失败: {e}')
        sys.exit(1)

    payload = gen_payload(lvs, args.source, override, args.imported_at)
    if not payload:
        print('无 payload 生成')
        sys.exit(1)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(payload, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n已保存: {args.out} ({len(payload)} 关)')


if __name__ == '__main__':
    main()
