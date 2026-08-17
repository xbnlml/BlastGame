#!/usr/bin/env python3
"""监控 bot 批跑完成：轮询 bot 目录，检测到 5 档齐全时刷新池子+输出结果。

用法:
  python tools/monitor_bot.py "56,57,71" --tiers "1,3,5"
  python tools/monitor_bot.py "81" --tiers "1,2,3,4,5" --timeout 7200

--tiers 必填。
"""
import os, sys, time, glob, re, subprocess

REPO = r'C:\Users\Administrator\Documents\BlastGame'
BOT_DIR = os.path.join(REPO, 'telemetry', 'bot')
DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    '..', '..', '..', '..', '..',
                    'download', 'Hermes', 'tools', 'dump_level_pools.py')


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
    parser.add_argument('--tiers', default='', help='必填')
    parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args()
    if not args.tiers:
        parser.error('--tiers 必填')

    LEVELS = set(parse_levels(args.levels))
    expected = len(args.tiers.split(','))
    print('[monitor] 监控 {} 档 {} 关, timeout={}s'.format(expected, len(LEVELS), args.timeout))

    pre_dirs = set(os.listdir(BOT_DIR)) if os.path.isdir(BOT_DIR) else set()
    print('[monitor] 当前 {} 个 bot 目录'.format(len(pre_dirs)))

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        current = set(os.listdir(BOT_DIR))
        for d in sorted(current - pre_dirs, reverse=True):
            dp = os.path.join(BOT_DIR, d)
            if not os.path.isdir(dp):
                continue
            dlv = set(p for p in d.replace('-','_').split('_') if p.isdigit() and p in LEVELS)
            if not dlv:
                continue
            tiers = [t for t in os.listdir(dp) if os.path.isdir(os.path.join(dp, t)) and re.search(r'T\d+', t)]
            done = sum(1 for t in tiers if glob.glob(os.path.join(dp, t, 'campaign-summary-*.csv')))
            if done >= expected:
                print('[monitor] ✅ {} 共 {} 档完成'.format(d, done))
                if os.path.exists(DUMP):
                    subprocess.run([sys.executable, '-X', 'utf8', DUMP], capture_output=True)
                for td in sorted(os.listdir(dp)):
                    m = re.search(r'T(\d+)', td)
                    if not m: continue
                    for sf in glob.glob(os.path.join(dp, td, 'campaign-summary-*.csv')):
                        with open(sf, encoding='utf-8-sig') as f:
                            import csv
                            for row in csv.DictReader(f):
                                lv = row.get('level','')
                                wr = row.get('winkate','')
                                if lv and wr:
                                    print('  L{} T{}: {:.1f}%'.format(lv, m.group(1), float(wr)*100))
                sys.exit(0)
        time.sleep(10)

    print('[monitor] ❌ 超时 {}s'.format(args.timeout))
    sys.exit(1)
