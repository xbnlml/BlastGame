#!/usr/bin/env python3
"""监控 bot 批跑完成：轮询 bot 目录，检测到 5 档齐全时刷新池子+输出结果。

用法:
  python tools/monitor_bot.py 56,57,71,86
  python tools/monitor_bot.py 89,90,91,95,99,100 --games 400 --timeout 7200
  python tools/monitor_bot.py 56 --tiers 1,3  # 只等指定档位
"""
import os, sys, time, glob, re, subprocess, json
from datetime import datetime

REPO = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
BOT_DIR = os.path.join(REPO, 'telemetry', 'bot')


def parse_levels(spec):
    levels = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            levels.extend(str(i) for i in range(int(a), int(b)+1))
        else:
            levels.append(part)
    return levels


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='监控 bot 批跑完成')
    parser.add_argument('levels', help='关卡范围')
    parser.add_argument('--games', type=int, default=400)
    parser.add_argument('--tiers', default='1,2,3,4,5')
    parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args()

    LEVELS = set(parse_levels(args.levels))
    tier_list = args.tiers.split(',')
    expected = len(tier_list)
    timeout = args.timeout

    # 记录批跑前的目录状态
    pre_dirs = set(os.listdir(BOT_DIR)) if os.path.isdir(BOT_DIR) else set()
    print('[monitor] 监控 {} 档 {} 关, timeout={}s'.format(expected, len(LEVELS), timeout))
    print('[monitor] 当前 {} 个 bot 目录'.format(len(pre_dirs)))

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not os.path.isdir(BOT_DIR):
            time.sleep(10)
            continue
        current = set(os.listdir(BOT_DIR))
        new = current - pre_dirs
        for d in sorted(new, reverse=True):
            dp = os.path.join(BOT_DIR, d)
            if not os.path.isdir(dp):
                continue
            # 检查目录是否包含被监控的关卡
            dir_levels = set()
            for part in d.replace('-', '_').split('_'):
                if part.isdigit() and part in LEVELS:
                    dir_levels.add(part)
            if not dir_levels:
                continue

            # 统计已完成的档位子目录
            tier_dirs = [td for td in os.listdir(dp)
                         if os.path.isdir(os.path.join(dp, td)) and re.search(r'T\d+', td)]
            done = 0
            for td in tier_dirs:
                csvs = glob.glob(os.path.join(dp, td, "campaign-summary-*.csv"))
                if csvs:
                    done += 1

            if done >= expected:
                print('[monitor] ✅ {} 共 {} 档完成'.format(d, done))
                # 刷新池子
                dump = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dump_level_pools.py')
                if os.path.exists(dump):
                    subprocess.run([sys.executable, '-X', 'utf8', dump], capture_output=True)

                # 输出结果
                for td in sorted(os.listdir(dp)):
                    tdir = os.path.join(dp, td)
                    if not os.path.isdir(tdir):
                        continue
                    m = re.search(r'T(\d+)', td)
                    if not m:
                        continue
                    for sf in glob.glob(os.path.join(tdir, "campaign-summary-*.csv")):
                        with open(sf, encoding='utf-8-sig') as f:
                            import csv
                            for row in csv.DictReader(f):
                                lv = row.get('level', '')
                                wr = row.get('winkate', '')
                                if lv in LEVELS and wr:
                                    print('  L{} T{}: {:.1f}%'.format(lv, m.group(1), float(wr)*100))

                sys.exit(0)

        elapsed = int(time.time() - (deadline - timeout))
        if elapsed % 30 == 0 and elapsed > 0:
            print('[monitor] {}s elapsed, 等待中...'.format(elapsed), flush=True)
        time.sleep(10)

    print('[monitor] ❌ 超时 {}s'.format(timeout))
    sys.exit(1)
