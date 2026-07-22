"""统一数据池接口

从所有数据源聚合可靠/参考数据，去重后输出。
"""
import json, os
from collections import defaultdict

STAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'stage-data')


def _lv_path(lv, suffix='.json'):
    return os.path.join(STAGE_DIR, str(lv), f'{lv}{suffix}')

def _norm_of(v):
    try: return str(float(v))
    except: return v

def _config_key(r):
    return (r.get('sd', ''), r.get('sc', ''), r.get('ratios', ''), _norm_of(r.get('of', '')))

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []

def save_json(path, data):
    import json
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_bot_data(lv):
    """读取 bot-only 数据"""
    return load_json(_lv_path(lv, '.bot.json'))

def save_bot_data(lv, records):
    """写入 bot 数据，同时从 assist 中删除同配置记录"""
    # Dedup within bot records (newest created_at wins for same config)
    seen = {}
    for r in records:
        key = _config_key(r)
        if key not in seen or r.get('created_at', '') > seen[key].get('created_at', ''):
            seen[key] = r
    # Cross-dedup: remove matching configs from assist
    bot_keys = set(seen.keys())
    assist = load_assist_data(lv)
    assist = [r for r in assist if _config_key(r) not in bot_keys]
    save_json(_lv_path(lv, '.assist.json'), assist)
    # Write bot data
    save_json(_lv_path(lv, '.bot.json'), list(seen.values()))
    return list(seen.values())

def load_assist_data(lv):
    """读取 assistant 数据 (summary + phase2)"""
    fp = _lv_path(lv, '.assist.json')
    # Fallback: if bot.json path (typo) was used somehow
    return load_json(fp)

def save_assist_data(lv, records):
    """写入 assist 数据，跳过 bot 已有的同配置"""
    # Dedup within assist (lowest priority wins)
    from collections import defaultdict
    groups = defaultdict(list)
    for r in records:
        key = _config_key(r)
        groups[key].append(r)
    deduped = []
    for key, group in groups.items():
        group.sort(key=lambda x: _source_penalty(x.get('source',''), x.get('totalGames',0)))
        deduped.append(group[0])
    # Cross-dedup: skip configs already in bot
    bot_keys = set()
    bot = load_bot_data(lv)
    for r in bot:
        bot_keys.add(_config_key(r))
    deduped = [r for r in deduped if _config_key(r) not in bot_keys]
    save_json(_lv_path(lv, '.assist.json'), deduped)
    return deduped

def load_ref_data(lv):
    """读取 phase1 参考数据"""
    return load_json(_lv_path(lv, '.ref.json'))

def save_ref_data(lv, records):
    save_json(_lv_path(lv, '.ref.json'), records)

def load_stage_data(lv):
    """加载旧格式兼容（读单一 json），如果新格式存在则合并"""
    bot = load_bot_data(lv)
    assist = load_assist_data(lv)
    ref = load_ref_data(lv)
    if bot or assist or ref:
        return {'reliable': bot + assist, 'reference': ref}
    # Old format fallback
    fp = _lv_path(lv)
    if os.path.exists(fp):
        with open(fp) as f:
            return json.load(f)
    return {'reliable': [], 'reference': []}


def get_all_records(lv):
    """获取单关全部可靠+参考数据，合并为列表（兼容旧代码）"""
    d = load_stage_data(lv)
    rel = d.get('reliable', [])
    ref = d.get('reference', [])
    return rel + ref

def get_bot_records(lv):
    """仅获取 bot 已验证数据"""
    return load_bot_data(lv)

def get_assist_records(lv):
    """仅获取辅助数据 (summary + phase2)"""
    return load_assist_data(lv)

def get_preferred_records(lv):
    """获取优先数据：bot 优先，assist 补充，ref 垫底"""
    bot = load_bot_data(lv)
    assist = load_assist_data(lv)
    ref = load_ref_data(lv)
    bot_keys = set()
    for r in bot:
        bot_keys.add(_config_key(r))
    assist = [r for r in assist if _config_key(r) not in bot_keys]
    assist_keys = set(_config_key(r) for r in assist)
    ref = [r for r in ref if _config_key(r) not in bot_keys and _config_key(r) not in assist_keys]
    return bot + assist + ref


def dedup_records(records):
    """按 (sd, sc, ratios, of) 去重，保留来源+局数最可靠的；同可靠性取最新批次"""
    seen = {}
    for r in records:
        key = (r.get('sd', ''), r.get('sc', ''), r.get('ratios', ''), _norm_of(r.get('of', '')))
        pen = _source_penalty(r.get('source', ''), r.get('totalGames', 0))
        if key not in seen:
            seen[key] = r
        elif pen < _source_penalty(seen[key].get('source', ''), seen[key].get('totalGames', 0)):
            seen[key] = r
        elif pen == _source_penalty(seen[key].get('source', ''), seen[key].get('totalGames', 0)) and r.get('created_at', '') > seen[key].get('created_at', ''):
            seen[key] = r
    return list(seen.values())


def _gap_score(wrs, difficulty='hard'):
    """档差品质分：越低越好。在最优区间 0 分，偏出按距离罚分，硬违规重罚。
    
    Normal (3-tier): 不罚 gap 上限，因为只有 3 档有效，T1→T3、T3→T5 可自然达到 30-50pp。
    """
    score = 0
    is_normal = difficulty == 'normal'
    if is_normal:
        gaps = [(0, 2, wrs[0] - wrs[2]), (2, 4, wrs[2] - wrs[4])]
    else:
        gaps = [(i, i+1, wrs[i] - wrs[i+1]) for i in range(4)]

    for i, j, g in gaps:
        hi = wrs[i]
        # 硬违规：<5% 重罚
        if g < 5:
            score += (5 - g) * 20
        # gap 上限：仅 Hard/SuperHard 有 >40% 处罚，Normal 不罚
        if not is_normal and g > 40:
            score += (g - 40) * 10
        # 档差优先：gap<15 连续罚分，gap<10 额外加罚
        if hi > 50:
            if g < 15:
                score += (15 - g) * 5  # 基本：每缺 1pp = 5 分
            if g < 10:
                score += (10 - g) * 10  # 额外：gap<10 再加一层
            if g > 35: score += (g - 35) * 3
        else:
            if g < 5: pass  # 已在硬违规处理
            if g < 10: score += (10 - g) * 3
            if g > 25: score += (g - 25) * 3
    return score


def _source_penalty(source, games):
    """按来源+局数计算优先级：越小越可靠。
    局数分档: ≥400(0), 300-399(1), 200-299(2), <200(3)
    来源排名: bot(0), summary(1), phase0(2), phase2(3), phase1(4)
    """
    tier = 0 if games >= 400 else (1 if games >= 300 else (2 if games >= 200 else 3))
    rank = {'bot': 0, 'summary': 1, 'phase0': 2, 'phase2': 3, 'phase1': 4}.get(source, 5)
    return tier * 5 + rank


def _bucket(records, target, window=50, size=60):
    """取目标窗口内的记录，按距离排序取前 size 条。"""
    bucket = [r for r in records if abs(r['wr'] - target) <= window]
    if not bucket:
        return []
    bucket.sort(key=lambda r: (abs(r['wr'] - target), _source_penalty(r.get('source',''), r.get('totalGames',0))))
    return bucket[:size]


def find_best_monotonic(records, targets, top_n=1, difficulty='hard'):
    """找最佳单调组合。

    Normal: 3-tier 窗口剪枝 O(k^3)
    Hard/SuperHard: 5-tier 窗口剪枝 + 内层gap预剪 O(k^5)
    """
    if len(records) < 3:
        return []

    if difficulty == 'normal':
        return _find_monotonic_3tier(records, targets, top_n)

    sorted_recs = sorted(records, key=lambda x: -x['wr'])
    WINDOW = 50

    buckets = [_bucket(sorted_recs, t, WINDOW) for t in targets]
    if any(not b for b in buckets):
        return []

    candidates = []
    for r1 in buckets[0]:
        for r2 in buckets[1]:
            if r2['wr'] > r1['wr']: continue
            g12 = r1['wr'] - r2['wr']
            if g12 < 5 or g12 > 40: continue
            for r3 in buckets[2]:
                if r3['wr'] > r2['wr']: continue
                g23 = r2['wr'] - r3['wr']
                if g23 < 5 or g23 > 40: continue
                for r4 in buckets[3]:
                    if r4['wr'] > r3['wr']: continue
                    g34 = r3['wr'] - r4['wr']
                    if g34 < 5 or g34 > 40: continue
                    for r5 in buckets[4]:
                        if r5['wr'] > r4['wr']: continue
                        g45 = r4['wr'] - r5['wr']
                        if g45 < 5 or g45 > 40: continue
                        recs5 = [r1, r2, r3, r4, r5]
                        keys = [_config_key(r) for r in recs5]
                        if len(set(keys)) < 5: continue
                        wrs = [r['wr'] for r in recs5]
                        target_score = sum(abs(wrs[i] - targets[i]) for i in range(5))
                        source_score = sum(_source_penalty(r.get('source',''), r.get('totalGames',0)) for r in recs5) * 0.3
                        gap_score = _gap_score(wrs, difficulty)
                        # 死亡分布分散度
                        dp = recs5[0].get('deathProfile')
                        death_score = 0
                        if dp:
                            worst = max(dp['early'], dp['transition'], dp['mid'], dp['late'])
                            if worst < 0.5:
                                death_score = -2
                            elif worst > 0.8:
                                death_score = 3
                        q = target_score + source_score + gap_score + death_score
                        gs = [g12, g23, g34, g45]
                        candidates.append((q, gs, recs5))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[:top_n]
    return []


def _find_monotonic_3tier(records, targets, top_n=1):
    """Normal 难度专用：T1=T2, T4=T5，窗口剪枝 O(k^3)。"""
    sorted_recs = sorted(records, key=lambda x: -x['wr'])
    t1, t3, t5 = targets[0], targets[2], targets[4]
    WINDOW = 50

    b1 = _bucket(sorted_recs, t1, WINDOW)
    b3 = _bucket(sorted_recs, t3, WINDOW)
    b5 = _bucket(sorted_recs, t5, WINDOW)
    if not (b1 and b3 and b5):
        return []

    candidates = []
    for r1 in b1:
        for r3 in b3:
            if r3['wr'] > r1['wr']: continue
            g13 = r1['wr'] - r3['wr']
            if g13 < 5: continue
            for r5 in b5:
                if r5['wr'] > r3['wr']: continue
                g35 = r3['wr'] - r5['wr']
                if g35 < 5: continue
                recs5 = [r1, r1, r3, r5, r5]
                wrs = [r1['wr'], r1['wr'], r3['wr'], r5['wr'], r5['wr']]
                target_score = abs(wrs[0]-targets[0]) + abs(wrs[2]-targets[2]) + abs(wrs[4]-targets[4])
                source_score = sum(_source_penalty(r.get('source',''), r.get('totalGames',0)) for r in [r1, r3, r5]) * 0.3
                gap_score = _gap_score(wrs, 'normal')
                q = target_score + source_score + gap_score
                candidates.append((q, [g13, g35, 0, 0], recs5))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[:top_n]
    return []
