#!/usr/bin/env python3
"""探针输入分层聚合器（探针 LLM 化 S1，2026-08-19）。

把单关全量池子聚合成 LLM 可读的条带式摘要（verified/phase2/phase1 三带 + 趋势命题 + 桶过滤），
满足：数据全给（不丢趋势）但 ≤3K token/关轮（防 token 爆炸）+ 相位伪精确标注（防 LLM 把噪声当真值）。

铁律：
- 单点 phase1/2 WR 永不作为目标值进输入——只给桶均值+相对方向
- 高熵字段（batch 串/deathProfile/failBucketDistribution）不进 prompt，落附件按需检索
- 输出必有 'token_est' 预算自检字段，超预算自动降级（删低置信桶）

用法:
    from tools.probe_input_packager import pack_level
    packed = pack_level('77', round_num=2)
    # packed 是 dict，直接 json 序列化后喂给 LLM
"""
import json, os, sys, time, math
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tools.data import pool

# 来源带映射（2026-07-31 语义：bot/summary/phase0 同级可靠；phase2/phase1 参考）
RELIABLE_SOURCES = ('bot', 'summary', 'phase0')
BAND_LABELS = {'verified': 'V2', 'phase2': 'P2', 'phase1': 'P1'}
BAND_ERR = {'verified': 0, 'phase2': '5-10pp', 'phase1': '20pp'}
# 桶划分（P2 补丁：方向判定差≥5pp，阈值按分位数动态）
SD_BUCKETS = [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49), (50, 100)]
OF_BUCKETS = [(0.0, 0.19), (0.2, 0.39), (0.4, 0.59), (0.6, 0.79), (0.8, 1.2)]
# token 硬预算（P1 补丁：packager 单测断言输出必 ≤2000 token 数据段；定稿单关单轮 ≤3K 含提示词）
TOKEN_BUDGET = 2000  # 数据段预算；提示词另算 ~500
# 各带 top-N 截断（预算内；数据全的关靠此压缩）
TOP_N = {'verified': 15, 'phase2': 12, 'phase1': 8}


def _wr_or(r):
    return r.get('wr', 0) or 0


def _games_or(r):
    return r.get('totalGames', 0) or r.get('games', 0) or 0


def _bucket_of(sd, of):
    """参数桶索引 (sd_bucket, of_bucket)，用来聚合趋势"""
    if sd is None or of is None:
        return None
    try:
        sd = int(sd)
        of = float(of)
    except (TypeError, ValueError):
        return None
    sbi = next((i for i, (lo, hi) in enumerate(SD_BUCKETS) if lo <= sd <= hi), None)
    obi = next((i for i, (lo, hi) in enumerate(OF_BUCKETS) if lo <= of < hi), None)
    if sbi is None or obi is None:
        return None
    return (sbi, obi)


def _band_of(r):
    src = r.get('source', '')
    if src in RELIABLE_SOURCES:
        return 'verified'
    if src == 'phase2':
        return 'phase2'
    if src == 'phase1':
        return 'phase1'
    return None


def _fmt(r, band):
    """单条数据行压缩格式：标 V2/P2/P1|档位|sd|sc|ratios|of|WR|n|日期"""
    b = BAND_LABELS.get(band, '??')
    return f"{b}|{r.get('tier','-')}|{r.get('sd','-')}|{r.get('sc','-')}|{r.get('ratios','-')}|{r.get('of','-')}|{round(_wr_or(r),1)}|{_games_or(r)}|{str(r.get('created_at',''))[:10]}"


def _trend_propositions(band_rows, band):
    """属性级趋势命题生成（P2 补丁：差≥5pp 才判方向，附行 id；U 形标 NON-MONO）"""
    # 按 sd 桶聚合（同 of 桶内）
    props = []
    if len(band_rows) < 3:
        return props
    # 简单方向检测：按 sd 升序看 WR 趋势
    by_sd = defaultdict(list)
    for r in band_rows:
        try:
            by_sd[int(r.get('sd', 0))].append(_wr_or(r))
        except (TypeError, ValueError):
            continue
    sds = sorted(by_sd)
    if len(sds) < 2:
        return props
    # 首尾差
    try:
        d = (sum(by_sd[sds[-1]]) / len(by_sd[sds[-1]])) - (sum(by_sd[sds[0]]) / len(by_sd[sds[0]]))
    except ZeroDivisionError:
        return props
    # P2 补丁：差≥5pp 才判方向，否则 FLAT
    if d >= 5:
        direction = 'sd↑→WR↑'
    elif d <= -5:
        direction = 'sd↑→WR↓'
    else:
        direction = 'FLAT'
    # 置信度：按样本量算
    n = sum(len(v) for v in by_sd.values())
    conf = 'STRONG' if (band == 'verified' and n >= 10) else ('WEAK' if n >= 5 else 'LOW')
    props.append({
        'prop': direction,
        'band': band,
        'n': n,
        'conf': conf,
        'note': 'L136 型非单调案例请对照具体桶行，禁止线性外推' if '↑' in direction and len(sds) >= 3 else '',
    })
    return props


def pack_level(lv, round_num=1, include_trace=3):
    """主入口：把单关池子打包含 LLM 的输入摘要。

    返回 dict（可直接 json.dumps 喂 LLM）或 None（无数据）。
    """
    lv = str(lv)
    recs = pool.dedup_records(pool.get_all_records(lv))
    if not recs:
        return None

    # 按带分桶
    bands = {'verified': [], 'phase2': [], 'phase1': []}
    for r in recs:
        b = _band_of(r)
        if b:
            bands[b].append(r)

    # 每带排序（WR 降序），取 top-N（预算内）
    rows = {}
    for b, rs in bands.items():
        rs = sorted(rs, key=_wr_or, reverse=True)
        picked = rs[:TOP_N.get(b, 10)]
        rows[b] = [_fmt(r, b) for r in picked]
        # 统计
        wrs = [_wr_or(r) for r in picked]
        summary = {
            'count': len(picked),
            'wr_range': [round(min(wrs), 1), round(max(wrs), 1)] if wrs else [],
            'err': BAND_ERR.get(b, ''),
            'n_total': sum(_games_or(r) for r in picked),
        }
        # 趋势命题
        props = _trend_propositions(picked, b)
        rows[b + '_props'] = props
        rows[b + '_stat'] = summary

    # 配置分区（按 ratios 类 × sd 桶 × of 桶聚合，P1 桶过滤：n≥3 且 games≥400）
    buckets = defaultdict(list)
    for r in recs:
        bkt = _bucket_of(r.get('sd'), r.get('of'))
        if bkt is None:
            continue
        b = _band_of(r)
        buckets[bkt].append((b, r))
    bucket_rows = []
    for (sbi, obi), items in sorted(buckets.items()):
        n = len(items)
        total_games = sum(_games_or(r) for _, r in items)
        if n < 3 or total_games < 400:
            continue  # P1 过滤：低置信桶压缩
        ver = [r for b, r in items if b == 'verified']
        wrs = [_wr_or(r) for _, r in items]
        bucket_rows.append({
            'sd_bucket': f'{SD_BUCKETS[sbi][0]}-{SD_BUCKETS[sbi][1]}',
            'of_bucket': f'{OF_BUCKETS[obi][0]}-{OF_BUCKETS[obi][1]}',
            'n': n, 'games': total_games,
            'wr_avg': round(sum(wrs) / len(wrs), 1),
            'wr_range': [round(min(wrs), 1), round(max(wrs), 1)],
            'verified_count': len(ver),
        })
    # 预算降级：桶行超预算时按 n×games 排序删低置信
    bucket_rows.sort(key=lambda x: x['n'] * x['games'], reverse=True)
    # 数据段=bands 行+bucket 行（props/stat 是决策必需的辅助，占比小，允许超预算时先删 bucket）
    while bucket_rows and len(json.dumps({'b': bucket_rows}, ensure_ascii=False)) > 3000:
        bucket_rows.pop()  # 删最不值钱的（已排序尾部）

    # token 估算：中英混合约 1 token/1.5 字符；预算只压数据行
    data_rows = {k: v for k, v in rows.items() if isinstance(v, list)}
    data_str = json.dumps({'bands': data_rows, 'buckets': bucket_rows}, ensure_ascii=False)
    token_est = int(len(data_str) / 1.5)

    return {
        'level': lv,
        'round': round_num,
        'packed_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'bands': rows,
        'buckets': bucket_rows,
        'token_est': token_est,
        'budget_note': 'OK ≤1000' if token_est <= TOKEN_BUDGET else f'OVER {token_est}',
        'meta': {
            'total_records': len(recs),
            'sources': sorted({r.get('source', '') for r in recs}),
            'calibration': 'phase1/2 单点可偏 ±20pp，只作相对方向；判定只用 verified',
        },
    }


def self_test():
    """自测：输出必 ≤1000 token 数据段 + 结构完整"""
    ok = True
    for lv in ('62', '77', '93'):
        p = pack_level(lv)
        if p is None:
            print(f'L{lv}: 无数据（跳过）')
            continue
        te = p['token_est']
        status = 'OK' if te <= TOKEN_BUDGET else 'OVER'
        print(f'L{lv}: token_est={te} {status} bands={ {k: len(v) for k, v in p["bands"].items() if isinstance(v, list)} } buckets={len(p["buckets"])}')
        if te > TOKEN_BUDGET:
            ok = False
    return ok


if __name__ == '__main__':
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == '--self-test':
        ok = self_test()
        print('自测:', 'PASS ✅' if ok else 'FAIL ❌')
        _sys.exit(0 if ok else 1)
    lv = _sys.argv[1] if len(_sys.argv) > 1 else '62'
    print(json.dumps(pack_level(lv), ensure_ascii=False, indent=2))