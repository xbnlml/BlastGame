#!/usr/bin/env python3
"""
dump_level_pools.py — 创建/更新 stage-data 数据池缓存

工作流数据中心 (Pool) 的构建脚本：
1. 调用 get_level_pool 读取 telemetry 原始数据（bot + opt）
2. 去重后写入 stage-data/{level}/{level}.json
3. 同时生成 stage-data/_summary.json 汇总表

每次运行只重新读取原始数据，完整刷新所有关卡的数据池。
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# 添加工具和上级目录到路径
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
PARENT_DIR = os.path.dirname(TOOLS_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from get_level_pool import (
    read_bot_attempts, read_opt_data, dedup_pools,
    parse_levels, print_summary_table, strip_meta
)

# stage-data 根目录（在 hermes 项目下）
STAGE_DIR = os.path.join(os.path.dirname(TOOLS_DIR), 'stage-data')


def get_level_range():
    """返回 L51-200 的 levels 列表"""
    return [str(i) for i in range(51, 201)]


def build_level_pools(levels, min_mtime_map=None):
    """构建所有关的数据池。

    min_mtime_map: {lv: timestamp} 时间防线，跳过该时间之前的目录数据
    返回: (reliable_dict, reference_dict)
    """
    if min_mtime_map is None:
        min_mtime_map = {}
    print('读取 bot 数据...')
    bot_data = read_bot_attempts(levels, min_mtime_map)
    print(f'  bot: {sum(len(v) for v in bot_data.values())} 条')

    print('读取 opt 数据...')
    opt_rel, opt_ref = read_opt_data(levels, min_mtime_map)
    print(f'  opt reliable: {sum(len(v) for v in opt_rel.values())} 条')
    print(f'  opt reference: {sum(len(v) for v in opt_ref.values())} 条')

    # 合并可靠池
    reliable = defaultdict(list)
    for lv in levels:
        if lv in bot_data:
            reliable[lv].extend(bot_data[lv])
        if lv in opt_rel:
            reliable[lv].extend(opt_rel[lv])

    # 去重
    print('去重中...')
    reliable, reference = dedup_pools(dict(reliable), dict(opt_ref))

    total_rel = sum(len(v) for v in reliable.values())
    total_ref = sum(len(v) for v in reference.values())
    print(f'  可靠池: {total_rel} 条')
    print(f'  参考池: {total_ref} 条')

    return reliable, reference


def write_josn_file(filepath, data):
    """写 JSON 文件，确保目录存在"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  ✅ {filepath}')


def dump_all_pools(reliable, reference):
    """写入所有关卡数据池到三文件分离格式：
       {lv}.bot.json — bot 验证数据
       {lv}.assist.json — summary + phase2 辅助数据
       {lv}.ref.json — phase1 参考数据"""
    levels = get_level_range()
    summary = {}

    from tools.data import pool as db

    for lv in levels:
        recs = reliable.get(lv, [])
        ref_recs = strip_meta(reference.get(lv, []))

        # Split by source
        bot_recs = strip_meta([r for r in recs if r.get('source') == 'bot'])
        assist_recs = strip_meta([r for r in recs if r.get('source') != 'bot'])

        bot_recs.sort(key=lambda x: -x['wr'])
        assist_recs.sort(key=lambda x: -x['wr'])
        ref_recs.sort(key=lambda x: -x['wr'])

        # Write via pool (cross-dedup happens here)
        db.save_bot_data(lv, bot_recs)
        db.save_assist_data(lv, assist_recs)
        db.save_ref_data(lv, ref_recs)

        # 摘要
        all_rel = bot_recs + assist_recs
        wrs = [r['wr'] for r in all_rel]
        n_bot = len(bot_recs)
        n_sum = sum(1 for r in assist_recs if r.get('source') == 'summary')
        n_ph2 = sum(1 for r in assist_recs if r.get('source') == 'phase2')

        summary[lv] = {
            'reliable_count': len(all_rel),
            'reference_count': len(ref_recs),
            'sources': {
                'bot': n_bot,
                'summary': n_sum,
                'phase2': n_ph2,
                'phase1': len(ref_recs),
            },
            'wr_min': round(min(wrs), 2) if wrs else None,
            'wr_max': round(max(wrs), 2) if wrs else None,
            'wr_span': round(max(wrs) - min(wrs), 2) if len(wrs) >= 2 else None,
        }

    # 写汇总
    total_rel = sum(s['reliable_count'] for s in summary.values())
    total_ref = sum(s['reference_count'] for s in summary.values())
    summary_meta = {
        'updated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'levels_covered': len(summary),
        'total_reliable': total_rel,
        'total_reference': total_ref,
        'levels': summary,
    }
    summary_path = os.path.join(STAGE_DIR, '_summary.json')
    write_josn_file(summary_path, summary_meta)

    print(f'\n总计: {len(summary)} 关, {total_rel} 条可靠, {total_ref} 条参考')


def print_stats(reliable, reference):
    """打印简要统计"""
    levels = get_level_range()
    print()
    print_summary_table(levels, reliable, reference)

    # 分档统计
    counts = defaultdict(int)
    for lv in levels:
        n = len(reliable.get(lv, []))
        if n == 0:
            counts['无数据'] += 1
        elif n < 5:
            counts['1-4条'] += 1
        elif n < 10:
            counts['5-9条'] += 1
        elif n < 20:
            counts['10-19条'] += 1
        else:
            counts['20+条'] += 1
    print('\n可靠池覆盖分布:')
    for k in ['无数据', '1-4条', '5-9条', '10-19条', '20+条']:
        if counts.get(k):
            print(f'  {k}: {counts[k]} 关')


def main():
    print('=' * 55)
    print('  dump_level_pools.py — 数据池缓存构建')
    print('=' * 55)
    print()

    levels = get_level_range()
    print(f'关卡范围: L{levels[0]} ~ L{levels[-1]} ({len(levels)} 关)')

    # 时间防线：动态读取每关 asset 文件 mtime（2026-08-04 新机制）
    # asset mtime 只反映"改关卡配置(牌面)"的时间——write_ddc 写 DDC 后恢复 mtime，
    # 不再污染。批次子目录时间 < asset mtime → 该关该批次数据无效（老牌面）。
    # 【补丁 2026-08-04】mtime 防线只对生效时刻之后修改的 asset 生效——
    # 生效时刻之前 write_ddc 已污染过 27 关的 mtime（8-04 写入时间），
    # 那些 mtime 不代表牌面修改时间，一律忽略；此刻之后 mtime 才可信。
    min_mtime_map = {}
    tracking_path = os.path.join(STAGE_DIR, '_last_refresh.json')
    manual_map = {}
    mtime_filter_since = None
    if os.path.isfile(tracking_path):
        try:
            tracking = json.load(open(tracking_path, encoding='utf-8'))
            updated_at = tracking.get('asset_updated_at', {})
            for lv, iso in updated_at.items():
                try:
                    manual_map[lv] = datetime.fromisoformat(iso).timestamp()
                except (ValueError, TypeError):
                    pass
            since = tracking.get('mtime_filter_since')
            if since:
                try:
                    mtime_filter_since = datetime.fromisoformat(since).timestamp()
                except (ValueError, TypeError):
                    pass
        except (json.JSONDecodeError, OSError):
            pass
    if mtime_filter_since is None:
        # 首次运行：记录生效时刻（此刻之前的 asset mtime 均不可信）
        mtime_filter_since = datetime.now().timestamp()
        try:
            tracking = json.load(open(tracking_path, encoding='utf-8')) if os.path.isfile(tracking_path) else {}
            tracking['mtime_filter_since'] = datetime.fromtimestamp(mtime_filter_since).isoformat()
            with open(tracking_path, 'w', encoding='utf-8') as f:
                json.dump(tracking, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
        print(f'mtime 防线生效时刻: {datetime.fromtimestamp(mtime_filter_since).isoformat()} (首次)')
    else:
        print(f'mtime 防线生效时刻: {datetime.fromtimestamp(mtime_filter_since).isoformat()}')

    # asset mtime 防线（自动，每关；仅生效时刻之后的 mtime 可信）
    from tools.asset_patcher import _asset_path
    auto_count = 0
    for lv in levels:
        ap = _asset_path(lv)
        if ap and os.path.isfile(ap):
            mt = os.path.getmtime(ap)
            if mt > mtime_filter_since:
                # 生效时刻之后修改过 → mtime 可信，作防线
                if lv in manual_map:
                    mt = max(mt, manual_map[lv])
                min_mtime_map[lv] = mt
                auto_count += 1
            elif lv in manual_map:
                # mtime 不可信（污染），但手动防线仍生效
                min_mtime_map[lv] = manual_map[lv]
    if min_mtime_map:
        print(f'时间防线激活: {len(min_mtime_map)} 关 (asset mtime 自动 {auto_count} + 手动兼容)')

    # 构建数据池
    reliable, reference = build_level_pools(levels, min_mtime_map)

    # 打印统计
    print_stats(reliable, reference)

    # 写入磁盘
    print(f'\n写入 {STAGE_DIR}/...')
    dump_all_pools(reliable, reference)

    print(f'\n✅ 完成！stage-data 已更新。')


if __name__ == '__main__':
    main()
