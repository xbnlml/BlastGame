"""telemetry/bot/ CSV 适配器

读取 campaign-attempts (ca-*.csv) 和 campaign-summary (cs-*.csv)，
按 (level, sd, sc, ratios, of) 聚合为 wr。
支持 Flat 和 Nested 两种目录结构。
"""
import os, csv, re
from collections import defaultdict

REPO = os.environ.get('BLASTGAME_REPO', os.path.join(os.path.expanduser('~'), 'Documents', 'BlastGame'))
BOT_DIR = os.path.join(REPO, 'telemetry', 'bot')

MIN_GAMES_RELIABLE = 400


def list_campaign_dirs():
    """列出 bot 目录下所有批次目录（跳过 _ 开头的）"""
    if not os.path.isdir(BOT_DIR):
        return []
    return sorted(d for d in os.listdir(BOT_DIR) if not d.startswith('_'))


def find_csv_files(batch_dir):
    """递归查找 ca- 或 campaign-attempts 文件"""
    files = []
    for root, dirs, fnames in os.walk(batch_dir):
        for f in fnames:
            if f.lower().startswith('ca-') or f.lower().startswith('campaign-attempts'):
                files.append(os.path.join(root, f))
    return sorted(files)


def find_summary_csv_files(batch_dir):
    """递归查找 cs- 或 campaign-summary 文件"""
    files = []
    for root, dirs, fnames in os.walk(batch_dir):
        for f in fnames:
            if f.lower().startswith('cs-') or f.lower().startswith('campaign-summary'):
                files.append(os.path.join(root, f))
    return sorted(files)


def parse_fail_bucket(fbd_str):
    """解析 failBucketDistribution 字符串为早/过渡/中/晚 四段占比。
    返回 {early, transition, mid, late}，数据缺失时返回 None。"""
    if not fbd_str:
        return None
    try:
        buckets = [float(x) for x in fbd_str.split(',')]
        if len(buckets) < 10:
            return None
        return {
            'early': round(sum(buckets[0:2]), 4),           # 桶 0-1（初始牌面）
            'transition': round(buckets[2], 4),              # 桶 2（过渡段）
            'mid': round(sum(buckets[3:6]), 4),              # 桶 3-5（中期）
            'late': round(sum(buckets[6:10]), 4),            # 桶 6-9（后期）
        }
    except (ValueError, TypeError):
        return None


def extract_tier_from_path(rel_path):
    """从相对路径中提取 T1-T5"""
    for t in ['T1', 'T2', 'T3', 'T4', 'T5']:
        pattern = f'{t}-' if t == 'T1' else f'-{t}-'
        if pattern in rel_path or f'_{t}-' in rel_path:
            return t
    return ''


def parse_ca_file(fp, levels=None):
    """解析单个 ca CSV，返回 {level: [(sd,sc,ratios,of,wr,totalGames,winGames), ...]}

    level=None → 所有关都读
    level=set   → 只读在 set 中的关
    """
    batch_dir = os.path.dirname(fp)
    rel_path = os.path.relpath(fp, BOT_DIR)
    tier = extract_tier_from_path(rel_path)

    groups = defaultdict(lambda: {'wins': 0, 'total': 0})

    with open(fp, 'r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            lv = row.get('level', '').strip()
            if levels is not None and lv not in levels:
                continue
            sd = (row.get('startDifficulty') or '').strip()
            sc = (row.get('shuffleSplitCount') or '').strip()
            ratios = (row.get('shuffleSplitRatios') or '').strip()
            of_val = (row.get('shuffleOverflowFactor') or '').strip()
            won = row.get('won', '').strip().lower()
            key = (lv, sd, sc, ratios, of_val)
            groups[key]['total'] += 1
            if won == 'true':
                groups[key]['wins'] += 1

    results = defaultdict(list)
    for (lv, sd, sc, ratios, of_val), g in groups.items():
        record = {
            'wr': round(g['wins'] / g['total'] * 100, 2) if g['total'] > 0 else 0,
            'sd': sd,
            'sc': sc,
            'ratios': ratios,
            'of': of_val,
            'totalGames': g['total'],
            'winGames': g['wins'],
            'tier': tier,
            'source': 'bot',
        }
        results[lv].append(record)

    return results


def read_all_bot_data(levels=None, min_mtime_map=None):
    """遍历所有 bot 目录，返回 {lv: [records]}"""
    import time
    from datetime import datetime

    results = defaultdict(list)
    for batch_name in list_campaign_dirs():
        bp = os.path.join(BOT_DIR, batch_name)
        if not os.path.isdir(bp):
            continue
        for fp in find_csv_files(bp):
            dir_mtime = os.path.getmtime(os.path.dirname(fp))
            created_at = datetime.fromtimestamp(dir_mtime).strftime('%Y-%m-%dT%H:%M:%S')
            parsed = parse_ca_file(fp, levels)
            for lv, recs in parsed.items():
                if min_mtime_map and lv in min_mtime_map and dir_mtime < min_mtime_map[lv]:
                    continue
                for r in recs:
                    r['_priority'] = 0 if r['totalGames'] >= MIN_GAMES_RELIABLE else 4
                    r['created_at'] = created_at
                results[lv].extend(recs)

    # 第二遍：读 summary CSV 补 failBucketDistribution
    for batch_name in list_campaign_dirs():
        bp = os.path.join(BOT_DIR, batch_name)
        if not os.path.isdir(bp):
            continue
        for fp in find_summary_csv_files(bp):
            try:
                with open(fp, 'r', encoding='utf-8-sig') as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        lv = row.get('level', '').strip()
                        if levels is not None and lv not in levels:
                            continue
                        sd = (row.get('startDifficulty') or '').strip()
                        sc = (row.get('shuffleSplitCount') or '').strip()
                        ratios = (row.get('shuffleSplitRatios') or '').strip()
                        of_val = (row.get('shuffleOverflowFactor') or '').strip()
                        fbd = parse_fail_bucket(row.get('failBucketDistribution', ''))
                        if not fbd:
                            continue
                        # 匹配到已有的 attempts 记录
                        for r in results.get(lv, []):
                            if str(r.get('sd','')) == sd and str(r.get('sc','')) == sc \
                                    and str(r.get('ratios','')) == ratios and str(r.get('of','')) == of_val:
                                if 'deathProfile' not in r:
                                    r['deathProfile'] = fbd
            except Exception:
                pass

    return results
