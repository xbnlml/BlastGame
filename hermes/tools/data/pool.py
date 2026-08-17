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
    """配置四元组键（sd/sc/ratios/of）。2026-08-06：sd/sc 统一 str()——
    read_ddc 返回 int（1）而池子存 str（'1'），类型不一致导致同配置匹配失败。"""
    return (str(r.get('sd', '')), str(r.get('sc', '')), str(r.get('ratios', '')), _norm_of(r.get('of', '')))


def _source_penalty(source, games):
    """按来源+局数计算优先级：越小越可靠。
    局数分档: >=400(0), 300-399(1), 200-299(2), <200(3)
    2026-07-31 语义：bot/summary/phase0 同级（rank 全 0）。
    2026-08-04 修正：同级来源不再按局数分档（penalty 全 0）——
    去重时同级比 created_at，新数据优先。phase1/phase2 仍按局数分档+来源罚。
    """
    rank = {'bot': 0, 'summary': 0, 'phase0': 0, 'phase2': 1, 'phase1': 2}.get(source, 3)
    if rank == 0:
        return 0
    tier = 0 if games >= 400 else (1 if games >= 300 else (2 if games >= 200 else 3))
    return tier * 5 + rank


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
    """写入 bot 数据。2026-07-31：不再 cross-dedup assist——
    去重统一交给 dedup_records（同级新数据优先），避免丢掉更新的 summary 数据"""
    seen = {}
    for r in records:
        key = _config_key(r)
        if key not in seen or r.get('created_at', '') > seen[key].get('created_at', ''):
            seen[key] = r
    save_json(_lv_path(lv, '.bot.json'), list(seen.values()))
    return list(seen.values())

def load_assist_data(lv):
    """读取 assistant 数据 (summary + phase2)"""
    fp = _lv_path(lv, '.assist.json')
    # Fallback: if bot.json path (typo) was used somehow
    return load_json(fp)

def save_assist_data(lv, records):
    """写入 assist 数据。2026-07-31：不再跳过 bot 同配置——
    去重统一交给 dedup_records（同级新数据优先）"""
    seen = {}
    for r in records:
        key = _config_key(r)
        if key not in seen or r.get('created_at', '') > seen[key].get('created_at', ''):
            seen[key] = r
    save_json(_lv_path(lv, '.assist.json'), list(seen.values()))
    return list(seen.values())

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


def filter_verified(records):
    """过滤只保留可入库数据源（bot/summary/phase0），排除 phase1/phase2。
    2026-07-31 铁则：phase1/phase2 任何情况下不能直接用于入库决策。
    """
    return [r for r in records if r.get('source') in ('bot', 'summary', 'phase0')]


def dedup_records(records):
    """按 (sd, sc, ratios, of) 去重。
    2026-08-04 规则：bot/summary/phase0 同级——同级时新数据优先（created_at 最新）；
    phase1/phase2 受罚（永不压过 bot/summary/phase0），phase1/phase2 之间按局数+新数据。
    2026-08-07 修复：键改用 _config_key（sd/sc 统一 str 规范化）——
    之前用原始类型做键，read_ddc 返回 int(sd=20) 与池子 str('20') 判定为两条，
    导致重复配置（审计 B1）。"""
    seen = {}
    for r in records:
        key = _config_key(r)
        pen = _source_penalty(r.get('source', ''), r.get('totalGames', 0))
        if key not in seen:
            seen[key] = r
        elif pen < _source_penalty(seen[key].get('source', ''), seen[key].get('totalGames', 0)):
            seen[key] = r
        elif pen == _source_penalty(seen[key].get('source', ''), seen[key].get('totalGames', 0)) and r.get('created_at', '') > seen[key].get('created_at', ''):
            seen[key] = r
    return list(seen.values())


# ─────────────────────────────────────────────────────────────
# 组合搜索算法已拆分到 tools/find_best_combo.py（2026-08-05 重构）。
# 本文件 pool.py 只保留「数据访问层」：读 stage-data JSON、去重、过滤。
# find_best_combo.py 承载：find_best_monotonic / _gap_score / target_pen_seg /
# _bucket / _find_monotonic_3tier，并作为独立 CLI 入口。
#
# 这里保留 find_best_monotonic 的延迟转发，保证 12 个调用方
# （agent_analyze/judge_level/design_probes/reimport_batch 等）
# 直接调 pool.find_best_monotonic 的行为不变（向后兼容）。
# 延迟 import 避免加载时循环依赖（find_best_combo 顶部会 import pool）。
# ─────────────────────────────────────────────────────────────

def find_best_monotonic(records, targets, top_n=1, difficulty='hard'):
    from tools.find_best_combo import find_best_monotonic as _fbm
    return _fbm(records, targets, top_n=top_n, difficulty=difficulty)
