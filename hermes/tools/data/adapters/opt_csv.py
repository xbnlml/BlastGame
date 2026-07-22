"""telemetry/multi-tier-opt/ 适配器

读取 summary-*.csv, phase2_candidates.csv, phase1_raw.csv。
自动检测 Phase2Appended 列偏移。
"""
import os, csv, re
from collections import defaultdict

REPO = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
OPT_DIR = os.path.join(REPO, 'telemetry', 'multi-tier-opt')


def list_opt_batches():
    if not os.path.isdir(OPT_DIR):
        return []
    return sorted(os.listdir(OPT_DIR))


def detect_phase2_shift(fieldnames):
    """检测 phase2_candidates.csv 是否有 Phase2Appended 列"""
    return 'Phase2Appended' in (fieldnames or [])


def read_summary_csv(fp, levels=None):
    """读 summary-*.csv（batch 级）"""
    results = defaultdict(list)
    if not os.path.isfile(fp):
        return results
    with open(fp, 'r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            lv = row.get('GameLevel', '').strip()
            if levels is not None and lv not in levels:
                continue
            wr_raw = row.get('WinRate', '')
            if not wr_raw:
                continue
            try:
                wr = float(wr_raw) * 100
            except:
                continue
            total_games = int(row.get('TotalRuns', 0) or 0)
            tier = row.get('Tier', '').strip()
            rec = {
                'wr': round(wr, 2),
                'sd': (row.get('StartDifficulty') or '').strip(),
                'sc': (row.get('ShuffleSplitCount') or '').strip(),
                'ratios': (row.get('ShuffleSplitRatios') or '').strip(),
                'of': (row.get('ShuffleOverflowFactor') or '').strip(),
                'totalGames': total_games,
                'tier': tier,
                'source': 'summary',
                '_priority': 1,
            }
            results[lv].append(rec)
    return results


def read_phase2_csv(fp, levels=None):
    """读 phase2_candidates.csv，自动检测列偏移"""
    results = defaultdict(list)
    if not os.path.isfile(fp):
        return results
    with open(fp, 'r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        shifted = 'Phase2Appended' in (reader.fieldnames or [])

        for row in reader:
            lv_raw = row.get('LevelGroup', '')
            # 从文件名路径取关卡号
            # phase2 文件在 {opt_dir}/{batch}/{lv}-{ts}/phase2_candidates.csv
            lv = os.path.basename(os.path.dirname(fp)).split('-')[0]
            if not lv.isdigit():
                continue
            if levels is not None and lv not in levels:
                continue
            wr_raw = row.get('WinRate', '')
            if not wr_raw:
                continue
            try:
                wr = float(wr_raw) * 100
            except:
                continue
            total_games = int(row.get('TotalRuns', 0) or 0)
            tier = row.get('Tier', '').strip()

            # Phase2Appended 列偏移修正
            has_pa = shifted and (row.get('Phase2Appended') or '').strip()
            rec = {
                'wr': round(wr, 2),
                'sd': (row.get('Phase2Appended') if has_pa else row.get('StartDifficulty') or '').strip(),
                'sc': (row.get('StartDifficulty') if has_pa else row.get('ShuffleSplitCount') or '').strip(),
                'ratios': (row.get('ShuffleSplitCount') if has_pa else row.get('ShuffleSplitRatios') or '').strip(),
                'of': (row.get('ShuffleSplitRatios') if has_pa else row.get('ShuffleOverflowFactor') or '').strip(),
                'totalGames': total_games,
                'tier': tier,
                'source': 'phase2',
                '_priority': 2,
            }
            results[lv].append(rec)
    return results


def read_phase1_csv(fp, levels=None):
    """读 phase1_raw.csv"""
    results = defaultdict(list)
    if not os.path.isfile(fp):
        return results
    with open(fp, 'r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            lv = row.get('GameLevel', '').strip()
            if levels is not None and lv not in levels:
                continue
            wr_raw = row.get('WinRate', '')
            wr_verified = row.get('VerifiedWinRate', '')
            wr_str = wr_verified or wr_raw
            if not wr_str:
                continue
            try:
                wr = float(wr_str) * 100
            except:
                continue
            total_games = int(row.get('TotalRuns', 0) or 0)
            rec = {
                'wr': round(wr, 2),
                'sd': (row.get('StartDifficulty') or '').strip(),
                'sc': (row.get('ShuffleSplitCount') or '').strip(),
                'ratios': (row.get('ShuffleSplitRatios') or '').strip(),
                'of': (row.get('ShuffleOverflowFactor') or '').strip(),
                'totalGames': total_games,
                'tier': '',
                'source': 'phase1',
                '_priority': 3,
            }
            results[lv].append(rec)
    return results


def read_per_level_subdirs(batch_dir, levels=None):
    """遍历批次的 per-level 子目录，读 summary + phase2 + phase1"""
    reliable = defaultdict(list)
    reference = defaultdict(list)
    for sub in sorted(os.listdir(batch_dir)):
        sp = os.path.join(batch_dir, sub)
        if not os.path.isdir(sp):
            continue
        lv = sub.split('-')[0]
        if not lv.isdigit():
            continue

        # per-level summary.csv
        sp_sum = os.path.join(sp, 'summary.csv')
        if os.path.isfile(sp_sum):
            results = read_summary_csv(sp_sum, levels)
            for l, recs in results.items():
                reliable[l].extend(recs)

        # phase2_candidates.csv
        sp_p2 = os.path.join(sp, 'phase2_candidates.csv')
        if os.path.isfile(sp_p2):
            results = read_phase2_csv(sp_p2, levels)
            for l, recs in results.items():
                reliable[l].extend(recs)

        # phase1_raw.csv
        sp_p1 = os.path.join(sp, 'phase1_raw.csv')
        if os.path.isfile(sp_p1):
            results = read_phase1_csv(sp_p1, levels)
            for l, recs in results.items():
                reference[l].extend(recs)

    return reliable, reference


def read_all_opt_data(levels=None):
    """遍历所有 opt 批次"""
    reliable = defaultdict(list)
    reference = defaultdict(list)
    for batch_name in list_opt_batches():
        bp = os.path.join(OPT_DIR, batch_name)
        if not os.path.isdir(bp):
            continue

        # batch-level summary
        for fname in os.listdir(bp):
            if fname.startswith('summary-') and fname.endswith('.csv') and 'status' not in fname:
                results = read_summary_csv(os.path.join(bp, fname), levels)
                for l, recs in results.items():
                    for r in recs:
                        r['batch'] = batch_name
                    reliable[l].extend(recs)

        # per-level subdirs
        rl, rf = read_per_level_subdirs(bp, levels)
        for l, recs in rl.items():
            reliable[l].extend(recs)
        for l, recs in rf.items():
            reference[l].extend(recs)

    return reliable, reference
