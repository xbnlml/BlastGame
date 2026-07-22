#!/usr/bin/env python3
"""改关卡数据隔离：写入时间防线到 _last_refresh.json，下次 dump 自动过滤旧数据。

用法:
  python tools/retire_level.py 59 --reason "T1 ceiling"
  python tools/retire_level.py --list
  python tools/retire_level.py --check

原理：
  _last_refresh.json 的 asset_updated_at 记录关卡最后修改时间。
  dump_level_pools.py 构建池子时跳过该时间前的 bot 数据。
  不动原文件 —— 旧数据仍保留在 telemetry/bot/ 供查阅。
"""
import os, sys, json
from datetime import datetime, timezone

STAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'stage-data')
TRACKING_FILE = os.path.join(STAGE_DIR, '_last_refresh.json')
BOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'project-state', 'board.md')


def load_tracking():
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'asset_updated_at': {}}


def save_tracking(data):
    with open(TRACKING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clear_stage_data(lv_str):
    """清空该关卡的 stage-data 池子缓存"""
    d = os.path.join(STAGE_DIR, lv_str)
    if not os.path.isdir(d):
        return
    for fname in os.listdir(d):
        if fname.endswith('.json'):
            p = os.path.join(d, fname)
            with open(p, 'w', encoding='utf-8') as f:
                f.write('[]')


def get_retired_from_board():
    """从 board.md 读取改关卡列表"""
    lvs = []
    if not os.path.exists(BOARD_FILE):
        return lvs
    with open(BOARD_FILE, encoding='utf-8') as f:
        in_section = False
        for line in f:
            if '改关卡' in line:
                in_section = True
                for word in line.replace(',', ' ').split():
                    try:
                        lv = int(word)
                        if 51 <= lv <= 100:
                            lvs.append(str(lv))
                    except:
                        pass
                break
    return lvs


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='改关卡数据隔离 —— 写入时间防线')
    ap.add_argument('level', nargs='?', help='关卡号')
    ap.add_argument('--reason', default='', help='改关卡原因')
    ap.add_argument('--list', action='store_true', help='列出已设防线的关卡')
    ap.add_argument('--check', action='store_true', help='巡检 board 改关卡但未设防线的')
    ap.add_argument('--remove', metavar='LV', help='移除时间防线（恢复数据）')
    args = ap.parse_args()

    data = load_tracking()
    updated_at = data.get('asset_updated_at', {})

    if args.list:
        if not updated_at:
            print('(空)')
        else:
            for lv, ts in sorted(updated_at.items(), key=lambda x: int(x[0])):
                print('L{}: {}'.format(lv, ts))
        sys.exit(0)

    if args.check:
        retired = get_retired_from_board()
        missing = [lv for lv in retired if lv not in updated_at]
        if missing:
            print('{} 关未设防线: {}'.format(len(missing), ', '.join(missing)))
            print('补设: python tools/retire_level.py {}'.format(missing[0]))
            sys.exit(1)
        else:
            print('全部 {} 关已设防线'.format(len(retired)))
        sys.exit(0)

    if args.remove:
        if args.remove in updated_at:
            del updated_at[args.remove]
            data['asset_updated_at'] = updated_at
            save_tracking(data)
            print('L{} 防线已移除'.format(args.remove))
        else:
            print('L{} 没有防线记录'.format(args.remove))
        sys.exit(0)

    if not args.level:
        ap.print_help()
        sys.exit(1)

    lv = args.level
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated_at[lv] = now
    data['asset_updated_at'] = updated_at
    save_tracking(data)
    clear_stage_data(lv)
    print('L{} 时间防线: {} ({})'.format(lv, now, args.reason or '无备注'))
    print('stage-data 已清空。下次 dump_level_pools 自动过滤旧数据。')
