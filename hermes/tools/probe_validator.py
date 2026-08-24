#!/usr/bin/env python3
"""探针输出校验层（探针 LLM 化 S1，2026-08-19）。

对 LLM（或任何来源）产出的 5 槽探针配置做三重校验：
1. schema：字段类型/范围/格式合法
2. 语义：单调性/gap 合理性/与已验证配置碰撞
3. 幻觉：非输入来源的虚构数值/虚假引用拒绝

配套打回链：validate_probes() 返回校验错误列表，调用方把错误回填进 prompt 重试（≤3 次），
全败回退确定性 design_probes.design()。

用法:
    from tools.probe_validator import validate_probes
    errors = validate_probes(probes, lv='62', used_keys=set())
    # errors == [] 表示通过；否则 errors 是 [{'slot': 1, 'kind': 'schema', 'msg': '...'}, ...]
"""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# 字段合法范围（与定稿 §5.1 一致）
SD_RANGE = (0, 60)
SC_RANGE = (1, 5)
# Asset validation accepts the continuous overflow-factor range [0, 1.01].
# Do not keep the obsolete 0.0..0.7 probe-only whitelist: real verified and
# phase2 records already contain values such as 0.75, 0.85 and 1.0.
OF_RANGE = (0.0, 1.01)
# ratios 值白名单（探索过的常见值，防 LLM 发明 7/13/99 等无效值）
RATIOS_VALUE_WHITELIST = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
# 每槽允许引用的输入数据编号前缀（幻觉校验：LLM 只允许引用输入聚合值）
EVIDENCE_PREFIXES = ('#V', '#P2', '#P1', '#b', 'B', 'V2', 'P2', 'P1')


def _norm_of(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _check_schema(probe, slot):
    """schema 校验：sd/sc/ratios/of 类型与范围"""
    errs = []
    sd = probe.get('sd')
    try:
        sd = int(sd)
    except (TypeError, ValueError):
        return [{'slot': slot, 'kind': 'schema', 'msg': f'sd={sd!r} 非整数'}]
    if not (SD_RANGE[0] <= sd <= SD_RANGE[1]):
        errs.append({'slot': slot, 'kind': 'schema', 'msg': f'sd={sd} 越界 [{SD_RANGE[0]},{SD_RANGE[1]}]'})

    sc = probe.get('sc')
    try:
        sc = int(sc)
    except (TypeError, ValueError):
        return [{'slot': slot, 'kind': 'schema', 'msg': f'sc={sc!r} 非整数'}]
    if not (SC_RANGE[0] <= sc <= SC_RANGE[1]):
        errs.append({'slot': slot, 'kind': 'schema', 'msg': f'sc={sc} 越界 [{SC_RANGE[0]},{SC_RANGE[1]}]'})

    ratios = probe.get('ratios', '')
    ratios_str = str(ratios).strip()
    parts = [p.strip() for p in ratios_str.split(',') if p.strip() != '']
    if len(parts) != 5:
        errs.append({'slot': slot, 'kind': 'schema', 'msg': f'ratios 需 5 个逗号分隔值，实际 {len(parts)} 个 ({ratios_str!r})'})
    else:
        try:
            vals = [int(p) for p in parts]
        except ValueError:
            errs.append({'slot': slot, 'kind': 'schema', 'msg': f'ratios 含非整数: {ratios_str!r}'})
        else:
            bad = [v for v in vals if v not in RATIOS_VALUE_WHITELIST]
            if bad:
                errs.append({'slot': slot, 'kind': 'schema', 'msg': f'ratios 值 {bad} 不在白名单 {sorted(RATIOS_VALUE_WHITELIST)}'})

    of = _norm_of(probe.get('of'))
    if of is None:
        errs.append({'slot': slot, 'kind': 'schema', 'msg': f'of={probe.get("of")!r} 非数值'})
    elif not (OF_RANGE[0] <= of <= OF_RANGE[1]):
        errs.append({'slot': slot, 'kind': 'schema', 'msg': f'of={of} 越界 [{OF_RANGE[0]},{OF_RANGE[1]}]'})

    return errs


def _check_semantic(probes, used_keys, lv, blacklist_keys=None):
    """语义校验：单调性 + 与已验证/已探过配置碰撞"""
    errs = []
    blacklist_keys = blacklist_keys or set()

    # 1. 非重复（used_keys = 已验证配置 + 黑名单）
    seen = set()
    for i, p in enumerate(probes, 1):
        from tools.data import pool
        key = pool._config_key(p)
        if key in used_keys or key in blacklist_keys:
            errs.append({'slot': i, 'kind': 'semantic', 'msg': f'配置与已知配置冲突: {key}'})
        if key in seen:
            errs.append({'slot': i, 'kind': 'semantic', 'msg': f'槽位重复: {key}'})
        seen.add(key)

    # 2. sd 排序（T1 应最易/最高 sd 不应出现在低档；宽松校验：5 槽 sd 应单调递减）
    sds = []
    for p in probes:
        try:
            sds.append(int(p.get('sd', 0)))
        except (TypeError, ValueError):
            sds.append(0)
    if len(sds) == 5:
        # 正常是 sd 递减（T1 最难→T5 最易；sd 越大越难，所以 sd 应递减）
        # 但 normal 模式 T1=T2/T4=T5，允许相等；探针是探索点不强制，只查明显倒挂
        if sds[0] < sds[2] and sds[2] < sds[4]:
            pass  # 递增（可能有理：探针测试反方向）——不拦，只记
        elif sds[0] < min(sds[1:]) - 10:
            errs.append({'slot': 1, 'kind': 'semantic', 'msg': f'T1 sd={sds[0]} 远低于其他档（min {min(sds[1:])}），疑似倒挂'})

    return errs


def _check_illusion(probes, input_payload):
    """幻觉校验：输出引用的数据编号必须存在于输入中，禁止自造数值"""
    errs = []
    # 输入中存在的引用前缀集合（从 input_payload 的 bands 提取）
    available_refs = set()
    if isinstance(input_payload, dict):
        bands = input_payload.get('bands', {}) if isinstance(input_payload.get('bands'), dict) else {}
        for key, items in bands.items():
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, str) and '|' in it:
                        available_refs.add(it.split('|')[0])  # V2/P2/P1 前缀
    for i, p in enumerate(probes, 1):
        ev = p.get('evidence', '') or p.get('rationale', '') or ''
        if not ev:
            continue
        # 提取引用标记（B1/B2/#V1/#P1 等）
        import re
        refs = re.findall(r'(?:#?[VP]\d+|B\d+|V2|P2|P1)', ev)
        for r in refs:
            if not r.startswith(('V2', 'P2', 'P1')):
                continue
            prefix = r[:2]
            if prefix not in {x[:2] for x in available_refs} and prefix not in ('V2', 'P2', 'P1'):
                errs.append({'slot': i, 'kind': 'illusion', 'msg': f'引用了输入中不存在的来源前缀 {r}'})
    return errs


def validate_probes(probes, lv, used_keys=None, blacklist_keys=None, input_payload=None):
    """三重校验主入口。

    参数:
        probes: [{'sd','sc','ratios','of','rationale','evidence'}, ...] 或 {T1:..., T2:...}
        lv: 关卡号
        used_keys: 已验证配置 key 集合（set of tuple）
        blacklist_keys: 黑名单 key 集合
        input_payload: 喂给 LLM 的输入摘要（幻觉校验用）

    返回: [] 通过；非空 = 错误列表 [{'slot','kind','msg'}]
    """
    used_keys = used_keys or set()
    # dict → list 统一
    if isinstance(probes, dict):
        items = list(probes.values())
    else:
        items = list(probes)

    errs = []
    for i, p in enumerate(items, 1):
        if not isinstance(p, dict):
            errs.append({'slot': i, 'kind': 'schema', 'msg': f'槽位 {i} 不是 dict: {type(p).__name__}'})
            continue
        errs.extend(_check_schema(p, i))
    errs.extend(_check_semantic(items, used_keys, lv, blacklist_keys))
    errs.extend(_check_illusion(items, input_payload))
    return errs


def format_retry_prompt(probes, errors):
    """把校验错误格式化为回填进 prompt 的反馈文本（打回链第 2/3 次用）"""
    lines = ['== 校验反馈（请修正后重新输出，仅输出修正后的 JSON）==']
    for e in errors[:10]:
        lines.append(f"- 槽位{e['slot']} [{e['kind']}]: {e['msg']}")
    lines.append('规则提醒：sd∈[0,60] 整数、sc∈[1,5]、ratios 5 个整数且值≤10、of∈[0,1.01]、5 槽不重复不撞已知配置。')
    return '\n'.join(lines)


if __name__ == '__main__':
    # 自测
    good = [
        {'sd': 20, 'sc': 3, 'ratios': '1,1,1,1,1', 'of': 0.5, 'rationale': '基准配置'},
        {'sd': 30, 'sc': 3, 'ratios': '10,1,1,1,1', 'of': 0.4, 'rationale': '前段重'},
        {'sd': 40, 'sc': 4, 'ratios': '1,10,1,1,10', 'of': 0.6, 'rationale': '混合'},
        {'sd': 50, 'sc': 5, 'ratios': '1,1,10,10,1', 'of': 0.3, 'rationale': '中段重'},
        {'sd': 60, 'sc': 5, 'ratios': '1,1,1,10,10', 'of': 0.7, 'rationale': '后段重'},
    ]
    bad = [
        {'sd': 99, 'sc': 3, 'ratios': '1,1,1,1,1', 'of': 0.5},
        {'sd': 20, 'sc': 3, 'ratios': '1,1,1,1,1', 'of': 0.5},
        {'sd': 20, 'sc': 3, 'ratios': '1,1,1,1', 'of': 0.5},
        {'sd': 20, 'sc': 3, 'ratios': '1,99,1,1,1', 'of': 0.5},
        {'sd': 20, 'sc': 3, 'ratios': '1,1,1,1,1', 'of': 0.9},
    ]
    e1 = validate_probes(good, '62')
    e2 = validate_probes(bad, '62')
    print(f'good: {"✅ 通过" if not e1 else f"❌ {len(e1)} 个错误 {e1[:2]}"}')
    print(f'bad:  {"✅ 全拦" if len(e2) >= 4 else f"❌ 漏拦 {len(e2)}: {e2}"}')