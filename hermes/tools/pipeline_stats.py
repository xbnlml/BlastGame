"""pipeline_stats.py — 多档位批次趋势统计（可观测性）

统计 telemetry/multi-tier-opt/ 下所有批次：耗时、候选数、覆盖、判定结果。
用于发现"变慢/退化/覆盖缩水"趋势（2026-08-10 新增，对齐 agent 可观测性实践）。

用法：
  python tools/pipeline_stats.py                 # 全部批次摘要
  python tools/pipeline_stats.py --levels 110    # 只看某关
  python tools/pipeline_stats.py --detail        # 每关详细（候选数/覆盖）
"""
import csv, os, sys, json
from datetime import datetime

OPT_ROOT = r'C:\Users\Administrator\Documents\BlastGame\telemetry\multi-tier-opt'

def parse_batch_name(name):
    """批次目录名: '54_57_61_64_72_79_82-83_85_93_102-2026-08-07T10-34-05' → (levels, ts)"""
    try:
        parts = name.rsplit('-', 2)
        levels = parts[0].replace('_', ',')
        ts = parts[1] + '-' + parts[2]
        return levels, ts
    except Exception:
        return name, '?'

def batch_duration(batch_dir):
    """批次耗时：最早文件 mtime 到最晚（或 summary 时间）"""
    try:
        files = []
        for root, dirs, fnames in os.walk(batch_dir):
            for f in fnames:
                if f.endswith(('.csv', '.json')):
                    files.append(os.path.getmtime(os.path.join(root, f)))
        if not files:
            return None
        return (max(files) - min(files)) / 3600
    except Exception:
        return None

def read_summary_status(batch_dir):
    """读 summary-level-status-*.csv → {lv: (status, reason)}"""
    for f in os.listdir(batch_dir):
        if f.startswith('summary-level-status'):
            try:
                rows = list(csv.DictReader(open(os.path.join(batch_dir, f), encoding='utf-8')))
                return {r['GameLevel']: (r['Status'], r['Reason'][:60]) for r in rows}
            except Exception:
                return {}
    return {}

def count_phase1(batch_dir, lv):
    """phase1_raw 候选数"""
    for d in os.listdir(batch_dir):
        if d.startswith(lv + '-'):
            p1 = os.path.join(batch_dir, d, 'phase1_raw.csv')
            if os.path.exists(p1):
                try:
                    return sum(1 for _ in open(p1, encoding='utf-8')) - 1
                except Exception:
                    return 0
    return 0

def main():
    detail = '--detail' in sys.argv
    levels_filter = None
    if '--levels' in sys.argv:
        i = sys.argv.index('--levels')
        levels_filter = set(sys.argv[i + 1].split(','))

    batches = sorted([d for d in os.listdir(OPT_ROOT) if os.path.isdir(os.path.join(OPT_ROOT, d))], reverse=True)
    if not batches:
        print('无批次')
        return

    print(f"{'批次':<55} {'关数':>3} {'耗时(h)':>7}  {'判定(ok/fail)':<16}")
    print('-' * 100)
    for b in batches:
        bdir = os.path.join(OPT_ROOT, b)
        levels, ts = parse_batch_name(b)
        dur = batch_duration(bdir)
        status = read_summary_status(bdir)
        if levels_filter:
            status = {k: v for k, v in status.items() if k in levels_filter}
        ok = sum(1 for s, _ in status.values() if s == 'ok')
        fail = sum(1 for s, _ in status.values() if s != 'ok')
        dur_s = f'{dur:.1f}' if dur else '?'
        mark = ' ← 最新' if batches.index(b) == 0 else ''
        print(f"{b[:53]:<55} {len(status):>3} {dur_s:>7}  {ok}/{fail}{'':<12}{mark}")

    if detail:
        print('\n=== 每关明细（最新批次）===')
        latest = batches[0]
        ldir = os.path.join(OPT_ROOT, latest)
        status = read_summary_status(ldir)
        for lv, (s, reason) in sorted(status.items(), key=lambda x: int(x[0])):
            if levels_filter and lv not in levels_filter:
                continue
            n1 = count_phase1(ldir, lv)
            print(f'  L{lv}: {s} phase1候选={n1}  {reason}')

if __name__ == '__main__':
    main()