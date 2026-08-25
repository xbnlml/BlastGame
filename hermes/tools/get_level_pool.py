"""BlastGame 关卡配置-胜率数据池检索工具

从 telemetry/bot/ 和 telemetry/multi-tier-opt/ 遍历数据，
按历史兼容结构分两个采集池输出：

  reliable: bot / summary 等候选记录（局数写入 totalGames，低样本只降优先级）
  reference: phase1/phase2 等探索记录

这里的 reliable 是旧接口名，不代表可直接用于判定或入库。最终决策必须再经
tools.data.pool.filter_verified()，只保留当前牌面有效的 bot/summary/phase0。

每条记录 = (wr, sd, sc, ratios, of, totalGames, source_tier, source)
同一 (sd,sc,ratios,of) 只在最高优先级的池里保留一条。

用法:
  python get_level_pool.py 51-100              # 范围
  python get_level_pool.py 89,90,91            # 逗号分隔
  python get_level_pool.py 51-55 --table       # 表格输出
  python get_level_pool.py 51-55 --json-lv 55  # 指定关的 JSON 池
  python get_level_pool.py 51-55 --min-games 200  # 最低局数过滤
  python get_level_pool.py 51-55 --raw            # 不过滤(含低样本数据)
  python get_level_pool.py 51-55 --format=min     # 精简输出(仅汇总)
"""
import sys, os, csv, json, re
from collections import defaultdict
from datetime import datetime
from tools.asset_patcher import level_sig

REPO = os.environ.get('BLASTGAME_REPO', os.path.join(os.path.expanduser('~'), 'Documents', 'BlastGame'))

# ===== 参数 =====
MIN_GAMES_RELIABLE = 400  # 仅用于历史 _priority 分档，不是准入门槛

# ===== 机器人逻辑版本防线（2026-08-14 新增）=====
# 2026-08-13 14:36（北京时间）机器人（bot 批跑 + 多档位优化器共用引擎）逻辑改动，
# 该时刻之前所有批次数据按旧逻辑产出，全部作废，永不复用。
# 批次目录时间早于该时刻 → 整批跳过（对 bot 与 multi-tier-opt 同时生效）。
LOGIC_VERSION_SINCE = '2026-08-13T14:36:00+08:00'

def _logic_since_timestamp():
    """逻辑版本防线时间戳（北京时间）。解析失败时退回 1970（不拦截任何数据）。"""
    try:
        return datetime.fromisoformat(LOGIC_VERSION_SINCE).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _dir_timestamp(path):
    """从目录名解析批次时间戳（如 171-200-2026-07-31T11-03-24）。

    2026-08-03 修复：之前用 os.path.getmtime()——复制目录后 mtime 变新，
    导致时间防线失效（旧批次数据混入）。目录名里的时间戳才是真实批次时间。
    解析失败时回退 mtime。
    """
    name = os.path.basename(path)
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})', name)
    if m:
        try:
            y, mo, d, h, mi, s = m.groups()
            return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s)).timestamp()
        except ValueError:
            pass
    return os.path.getmtime(path)



def parse_levels(spec):
    levels = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            for lv in range(int(a), int(b) + 1):
                levels.add(str(lv))
        else:
            levels.add(part)
    return sorted(levels, key=int)


# ==============================
def parse_fbd(fbd_str):
    """返回 (10段原始串, 4段聚合deathProfile)；格式不合法返回 (None, None)"""
    if not fbd_str:
        return None, None
    try:
        buckets = [float(x) for x in fbd_str.split(',')]
        if len(buckets) < 10:
            return None, None
        raw = ','.join(f'{b:.3f}' for b in buckets[:10])
        dp = {
            'early': round(sum(buckets[0:2]), 4),
            'transition': round(buckets[2], 4),
            'mid': round(sum(buckets[3:6]), 4),
            'late': round(sum(buckets[6:10]), 4),
        }
        return raw, dp
    except (ValueError, TypeError):
        return None, None


# Bot 数据 (campaign-attempts)
# ==============================
def read_bot_attempts(levels, min_mtime_map=None):
    """读 campaign-attempts CSV，按 (sd,sc,ratios,of) 取最新批次数据。

    策略：
    1. 先按 (batch_dir, sd, sc, ratios, of) 分组聚合（同批次内合并）
    2. 再按 (sd, sc, ratios, of) 去重，只保留 created_at 最新的批次
    3. 旧批次数据自动丢弃

    min_mtime_map: {lv: timestamp} 时间防线，跳过该时间之前的目录数据

    支持两种目录结构：
      Flat:  L{range}-T{tier}-{ts}-batch-range/campaign-attempts-*.csv
      Nested: {level}-{level}-{ts}/L{range}-T{tier}-{ts}-batch-range/campaign-attempts-*.csv

    返回 { level: [record, ...] }
    每条 record 有: wr, sd, sc, ratios, of, totalGames, winGames, source_tier, source='bot'
    """
    bot_dir = os.path.join(REPO, 'telemetry', 'bot')
    results = defaultdict(list)
    if min_mtime_map is None:
        min_mtime_map = {}

    if not os.path.isdir(bot_dir):
        return results

    # 递归寻找所有 campaign-attempts CSV（支持 ca- 缩写）
    attempt_files = []
    for root, dirs, files in os.walk(bot_dir):
        for f in files:
            if f.endswith('.csv'):
                low = f.lower()
                if low.startswith('campaign-attempts') or low.startswith('ca-'):
                    attempt_files.append(os.path.join(root, f))

    # 阶段1：按 batch_dir 分组聚合（同批次内合并所有 CSV）
    # key = (batch_dir, lv, sd, sc, ratios, of)
    batch_groups = {}
    batch_created = {}  # batch_dir -> created_at

    # 关卡设计校验缓存: (top_batch_dir, lv) -> bool
    level_match_cache = {}

    for fp in sorted(attempt_files):
        batch_dir = os.path.dirname(fp)
        top_batch_dir = os.path.dirname(batch_dir)  # 顶层批次目录，含 level-assets/
        dir_mtime = _dir_timestamp(batch_dir)

        # 机器人逻辑版本防线（2026-08-14）：逻辑改动前的老批次整批作废
        if dir_mtime < _logic_since_timestamp():
            continue

        # 时间防线
        skip_batch = False
        if min_mtime_map and dir_mtime < max(v for v in min_mtime_map.values()):
            # 粗略跳过：如果该批次早于任意关的时间防线，逐行检查
            pass  # 逐行检查

        created_at = datetime.fromtimestamp(dir_mtime).strftime('%Y-%m-%dT%H:%M:%S')
        if batch_dir not in batch_created:
            batch_created[batch_dir] = created_at

        # 从相对路径中提取 tier
        rel_path = os.path.relpath(fp, bot_dir)
        tier = ''
        for t in ['T1-', 'T2-', 'T3-', 'T4-', 'T5-']:
            if t in rel_path:
                tier = t.replace('-', '')
                break

        with open(fp, 'r', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                lv = row.get('level', '').strip()
                if lv not in levels:
                    continue

                # 关卡设计校验：bot 快照 vs 当前 asset
                # 2026-08-04：无快照 → 信任（与 _opt_snapshot_valid 一致），
                # 有快照才比牌面——缺失快照时静默跳过会悄悄丢数据。
                cache_key = (top_batch_dir, lv)
                if cache_key not in level_match_cache:
                    snap_path = os.path.join(top_batch_dir, 'level-assets', 'test', lv + '.asset')
                    sig_snap = level_sig(snap_path)
                    sig_cur = level_sig(int(lv))
                    if sig_snap is None:
                        level_match_cache[cache_key] = True  # 无快照 → 信任
                    else:
                        level_match_cache[cache_key] = (sig_snap == sig_cur)
                if not level_match_cache[cache_key]:
                    continue  # 关卡设计已变，跳过该批次该关数据

                # 时间防线：检查该关是否有 min_mtime 阈值
                if lv in min_mtime_map and dir_mtime < min_mtime_map[lv]:
                    continue

                sd = row.get('startDifficulty', '').strip()
                sc = row.get('shuffleSplitCount', '').strip()
                ratios = row.get('shuffleSplitRatios', '').strip()
                of_val = row.get('shuffleOverflowFactor', '').strip()
                key = (batch_dir, lv, sd, sc, ratios, of_val)

                won = row.get('won', '').strip().lower()
                if key not in batch_groups:
                    batch_groups[key] = {'wins': 0, 'total': 0, 'source_tier': tier}
                batch_groups[key]['total'] += 1
                if won == 'true':
                    batch_groups[key]['wins'] += 1

    # 阶段2：按 (sd,sc,ratios,of) 去重，保留最新批次
    config_best = {}  # (lv, sd, sc, ratios, of) -> record
    for (batch_dir, lv, sd, sc, ratios, of_val), g in batch_groups.items():
        config_key = (lv, sd, sc, ratios, of_val)
        created_at = batch_created[batch_dir]
        wr = g['wins'] / g['total'] * 100
        record = {
            'wr': round(wr, 2),
            'sd': sd,
            'sc': sc,
            'ratios': ratios,
            'of': of_val,
            'totalGames': g['total'],
            'winGames': g['wins'],
            'source_tier': g['source_tier'],
            'source': 'bot',
            '_priority': 0 if g['total'] >= MIN_GAMES_RELIABLE else 4,
            'created_at': created_at,
        }
        if config_key not in config_best or created_at > config_best[config_key].get('created_at', ''):
            config_best[config_key] = record

    # 阶段3：填入 results
    for (lv, sd, sc, ratios, of_val), record in config_best.items():
        results[lv].append(record)

    # 阶段4：读 summary CSV 补 failBucketDistribution
    summary_files = []
    for root, dirs, files in os.walk(bot_dir):
        for f in files:
            if f.endswith('.csv'):
                low = f.lower()
                if low.startswith('campaign-summary') or low.startswith('cs-'):
                    summary_files.append(os.path.join(root, f))

    for fp in sorted(summary_files):
        try:
            with open(fp, 'r', encoding='utf-8-sig') as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    lv = row.get('level', '').strip()
                    if lv not in levels: continue
                    sd = (row.get('startDifficulty') or '').strip()
                    sc = (row.get('shuffleSplitCount') or '').strip()
                    ratios = (row.get('shuffleSplitRatios') or '').strip()
                    of_val = (row.get('shuffleOverflowFactor') or '').strip()
                    fbd_raw, fbd_dp = parse_fbd(row.get('failBucketDistribution', ''))
                    if not fbd_dp: continue
                    for r in results.get(lv, []):
                        if str(r.get('sd','')) == sd and str(r.get('sc','')) == sc \
                                and str(r.get('ratios','')) == ratios and str(r.get('of','')) == of_val:
                            if 'deathProfile' not in r:
                                r['deathProfile'] = fbd_dp
                            if 'failBucketDistribution' not in r and fbd_raw:
                                r['failBucketDistribution'] = fbd_raw
        except Exception:
            pass

    return results


# ==============================
# Opt 数据 (summary / phase2 / phase1_raw)
# ==============================
def _opt_snapshot_valid(bp, lv, cache, sub_ts=None):
    """批次有 asset 快照 → 对比关卡配置（牌面），一致才有效。

    2026-08-04 规则（用户确认）：
    - 数据（批次）有 asset 快照：直接对比快照 vs 当前 asset 的关卡配置
      （level_sig 剔除 scoreMultipliers + DynamicDifficultyConfigs，
      只比牌面：myStack/myStage/customCellDrawingListV2 等）。
      不一致 = 老牌面 = 数据无效，整批过滤。
      注：不做 mtime 可信度豁免——拷贝来的旧快照（如 7-31 文件）
      若与当前 asset 牌面不一致，说明该批次就是老牌面数据，应过滤。
    - 无快照：不判断（靠时间防线：批次时间 vs 关卡 asset 修改时间）。
    """
    key = (bp, lv)
    if key in cache:
        return cache[key]
    snap_path = None
    for sub in os.listdir(bp):
        sp = os.path.join(bp, sub)
        if os.path.isdir(sp) and sub.split('-')[0] == lv:
            cand = os.path.join(sp, 'level-assets', 'test', lv + '.asset')
            if os.path.isfile(cand):
                snap_path = cand
                break
    if snap_path is None:
        cache[key] = True  # 无快照，靠时间防线
        return True
    try:
        sig_snap = level_sig(snap_path)
        sig_cur = level_sig(int(lv))
    except Exception:
        cache[key] = True
        return True
    ok = sig_snap is not None and sig_snap == sig_cur
    cache[key] = ok
    return ok


def read_opt_data(levels, min_mtime_map=None):
    """读 multi-tier-opt 数据。

    返回 (reliable_dict, reference_dict)
    reliable: summary(rank=1) + phase2_candidates
    reference: phase1_raw + phase0_prior

    2026-08-04 注：牌面校验已撤销（level-assets 快照可能是旧拷贝、
    phase0_prior 只是难度参数，两者都不能证明跑批时关卡牌面一致）。
    数据有效性靠时间防线（min_mtime_map）+ 新数据优先去重兜底。
    """
    opt_dir = os.path.join(REPO, 'telemetry', 'multi-tier-opt')
    reliable = defaultdict(list)
    reference = defaultdict(list)
    if min_mtime_map is None:
        min_mtime_map = {}

    # 关卡牌面校验缓存: (batch_dir, lv) -> bool
    snapshot_cache = {}

    if not os.path.isdir(opt_dir):
        return reliable, reference

    # ---- 正式读取 ----
    for batch in sorted(os.listdir(opt_dir)):
        bp = os.path.join(opt_dir, batch)
        if not os.path.isdir(bp):
            continue
        batch_mtime = _dir_timestamp(bp)
        batch_created_at = datetime.fromtimestamp(batch_mtime).strftime('%Y-%m-%dT%H:%M:%S')

        # 机器人逻辑版本防线（2026-08-14）：逻辑改动前的老批次整批作废
        if batch_mtime < _logic_since_timestamp():
            continue

        # ---- batch-level summary ----
        for bs in [f for f in os.listdir(bp) if f.startswith('summary-') and f.endswith('.csv')]:
            with open(os.path.join(bp, bs), 'r', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    lv = row.get('GameLevel', '').strip()
                    if lv not in levels:
                        continue
                    if lv in min_mtime_map and batch_mtime < min_mtime_map[lv]:
                        continue
                    # batch-level summary：用批次目录名时间兜底做牌面校验
                    if not _opt_snapshot_valid(bp, lv, snapshot_cache):
                        continue  # 牌面不一致，跳过该关
                    rank = row.get('Rank', '').strip()
                    wr = float(row.get('VerifiedWinRate', 0)) * 100
                    tier = row.get('Tier', '').strip()
                    total_games = int(row.get('TotalRuns', 0))
                    fbd_raw, fbd_dp = parse_fbd(row.get('failBucketDistribution', ''))
                    rec = {
                        'wr': round(wr, 2),
                        'sd': row.get('StartDifficulty', '').strip(),
                        'sc': row.get('ShuffleSplitCount', '').strip(),
                        'ratios': (row.get('ShuffleSplitRatios') or '').strip(),
                        'of': (row.get('ShuffleOverflowFactor') or '').strip(),
                        'totalGames': total_games,
                        'source_tier': tier,
                        'source': 'summary',
                        'batch': batch,
                        '_priority': 1,
                        'created_at': batch_created_at,
                    }
                    if fbd_dp:
                        rec['deathProfile'] = fbd_dp
                    if fbd_raw:
                        rec['failBucketDistribution'] = fbd_raw
                    if rank == '1':
                        reliable[lv].append(rec)

        # ---- per-level subdirs ----
        for sub in sorted(os.listdir(bp)):
            sp = os.path.join(bp, sub)
            if not os.path.isdir(sp):
                continue
            lv = sub.split('-')[0]
            if lv not in levels:
                continue
            sub_mtime = _dir_timestamp(sp)
            sub_created_at = datetime.fromtimestamp(sub_mtime).strftime('%Y-%m-%dT%H:%M:%S')
            # 关卡牌面校验：快照（可信时）与当前 asset 不一致 → 整关跳过
            if not _opt_snapshot_valid(bp, lv, snapshot_cache, sub_ts=sub_mtime):
                continue  # 牌面不一致，该关所有数据无效（summary/phase2/phase1/phase0）

            # summary.csv
            sp_sum = os.path.join(sp, 'summary.csv')
            if os.path.isfile(sp_sum):
                with open(sp_sum, 'r', encoding='utf-8') as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        rank = row.get('Rank', '').strip()
                        wr = float(row.get('VerifiedWinRate', 0)) * 100
                        tier = row.get('Tier', '').strip()
                        total_games = int(row.get('TotalRuns', 0))
                        fbd_raw, fbd_dp = parse_fbd(row.get('failBucketDistribution', ''))
                        rec = {
                            'wr': round(wr, 2),
                            'sd': row.get('StartDifficulty', '').strip(),
                            'sc': row.get('ShuffleSplitCount', '').strip(),
                            'ratios': row.get('ShuffleSplitRatios', '').strip(),
                            'of': (row.get('ShuffleOverflowFactor') or '').strip(),
                            'totalGames': total_games,
                            'source_tier': tier,
                            'source': 'summary',
                            'batch': f'{batch}/{sub}',
                            '_priority': 1,
                            'created_at': sub_created_at,
                        }
                        if fbd_dp:
                            rec['deathProfile'] = fbd_dp
                        if fbd_raw:
                            rec['failBucketDistribution'] = fbd_raw
                        if lv in min_mtime_map and sub_mtime < min_mtime_map[lv]:
                            continue
                        if rank == '1':
                            reliable[lv].append(rec)

            # phase2_candidates.csv -> reliable
            sp_p2 = os.path.join(sp, 'phase2_candidates.csv')
            if os.path.isfile(sp_p2):
                with open(sp_p2, 'r', encoding='utf-8') as fh:
                    raw_lines = fh.readlines()
                if not raw_lines:
                    continue
                header_cols = len(raw_lines[0].strip().split(','))
                reader = csv.DictReader(raw_lines)
                for row in reader:
                    wr = float(row.get('WinRate', 0)) * 100
                    total_games = int(row.get('TotalRuns', 0))
                    tier = row.get('Tier', '').strip()
                    # 列偏移检测：数据行列数 < 表头列数 → Phase2Appended 列不输出，字段左移
                    data_cols = len([v for v in row.values() if v is not None])
                    shifted = data_cols < header_cols
                    if shifted:
                        sd = (row.get('Phase2Appended') or '').strip()
                        sc = (row.get('StartDifficulty') or '').strip()
                        ratios = (row.get('ShuffleSplitCount') or '').strip()
                        of = (row.get('ShuffleSplitRatios') or '').strip()
                    else:
                        sd = (row.get('StartDifficulty') or '').strip()
                        sc = (row.get('ShuffleSplitCount') or '').strip()
                        ratios = (row.get('ShuffleSplitRatios') or '').strip()
                        of = (row.get('ShuffleOverflowFactor') or '').strip()
                    rec = {
                        'wr': round(wr, 2),
                        'sd': sd,
                        'sc': sc,
                        'ratios': ratios,
                        'of': of,
                        'totalGames': total_games,
                        'source_tier': tier,
                        'source': 'phase2',
                        'batch': f'{batch}/{sub}',
                        '_priority': 3,
                        'created_at': sub_created_at,
                    }
                    if lv in min_mtime_map and sub_mtime < min_mtime_map[lv]:
                        continue
                    reliable[lv].append(rec)

            # phase1_raw.csv -> reference
            sp_p1 = os.path.join(sp, 'phase1_raw.csv')
            if os.path.isfile(sp_p1):
                with open(sp_p1, 'r', encoding='utf-8') as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        wr = float(row.get('WinRate', 0)) * 100
                        total_games = int(row.get('TotalRuns', 0))
                        rec = {
                            'wr': round(wr, 2),
                            'sd': row.get('StartDifficulty', '').strip(),
                            'sc': row.get('ShuffleSplitCount', '').strip(),
                            'ratios': row.get('ShuffleSplitRatios', '').strip(),
                            'of': (row.get('ShuffleOverflowFactor') or '').strip(),
                            'totalGames': total_games,
                            'source': 'phase1',
                            'batch': f'{batch}/{sub}',
                            '_priority': 4,
                            'created_at': sub_created_at,
                        }
                        if lv in min_mtime_map and sub_mtime < min_mtime_map[lv]:
                            continue
                        reference[lv].append(rec)

            # phase0_prior.csv -> reference
            sp_p0 = os.path.join(sp, 'phase0_prior.csv')
            if os.path.isfile(sp_p0):
                with open(sp_p0, 'r', encoding='utf-8') as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        wr = float(row.get('PriorWinRate', 0)) * 100
                        total_games = int(row.get('TotalRuns', 0))
                        if total_games < 100:
                            continue
                        tier = row.get('Tier', '').strip()
                        # 从 sub 目录名提取关卡号（如 "82-2026-07-19T02-50-11"）
                        lv_tag = sub.split('-')[0].lstrip('L')
                        if lv_tag not in levels:
                            continue
                        rec = {
                            'wr': round(wr, 2),
                            'sd': (row.get('StartDifficulty') or '').strip(),
                            'sc': (row.get('ShuffleSplitCount') or '').strip(),
                            'ratios': (row.get('ShuffleSplitRatios') or '').strip(),
                            'of': (row.get('ShuffleOverflowFactor') or '').strip(),
                            'totalGames': total_games,
                            'source_tier': tier,
                            'source': 'phase0',
                            'batch': f'{batch}/{sub}',
                            '_priority': 2,
                            'created_at': sub_created_at,
                        }
                        if lv_tag in min_mtime_map and sub_mtime < min_mtime_map[lv_tag]:
                            continue
                        # 2026-08-03 修复：phase0 是可靠数据（bot/summary/phase0 同级），
                        # 之前放 reference 会被 dedup_pools 当"可靠池已有配置"删掉（同配置时）。
                        # 放 reliable 后 dedup 按同级新数据优先，自动保留更新的 phase0。
                        reliable[lv_tag].append(rec)

    return reliable, reference


# ==============================
# 去重：同一 (sd,sc,ratios,of) 只保留最高优先级
# ==============================

def dedup_pools(reliable, reference):
    """去重：
    1. 可靠池内部：同一 (sd,sc,ratios,of) 按优先级 Bot > Summary > Phase2 保留一条
    2. 参考池：去掉可靠池已存在的配置
    """
    def _norm_of(v):
        try: return str(float(v))
        except: return v

    def dedup_by_priority(records):
        """按优先级去重：同一配置只保留可靠性最高的；同可靠性取最新批次"""
        from tools.data.pool import _source_penalty as _sp
        best = {}
        for rec in records:
            key = (rec['sd'], rec['sc'], rec['ratios'], _norm_of(rec['of']))
            pen = _sp(rec.get('source', ''), rec.get('totalGames', 0))
            if key not in best:
                best[key] = rec
            else:
                curr = best[key]
                if pen < _sp(curr.get('source', ''), curr.get('totalGames', 0)) or \
                   (pen == _sp(curr.get('source', ''), curr.get('totalGames', 0)) and rec.get('created_at', '') > curr.get('created_at', '')):
                    best[key] = rec
        return sorted(best.values(), key=lambda x: -x['wr'])

    # 可靠池内部去重
    new_reliable = {lv: dedup_by_priority(recs) for lv, recs in reliable.items()}

    # 参考池：去掉可靠池已存在的配置
    reliable_keys = set()
    for lv, recs in new_reliable.items():
        for rec in recs:
            reliable_keys.add((lv, rec['sd'], rec['sc'], rec['ratios'], _norm_of(rec['of'])))

    new_reference = {}
    for lv, recs in reference.items():
        filtered = []
        for rec in recs:
            key = (lv, rec['sd'], rec['sc'], rec['ratios'], _norm_of(rec['of']))
            if key not in reliable_keys:
                filtered.append(rec)
        new_reference[lv] = filtered

    return new_reliable, new_reference


def strip_meta(records):
    """去掉 _priority 等内部字段，只保留对外使用的字段"""
    result = []
    for rec in records:
        out = {}
        for k, v in rec.items():
            if not k.startswith('_'):
                out[k] = v
        result.append(out)
    return result


# ==============================
# 输出
# ==============================
def print_level_pool(lv, reliable, reference):
    """打印一关的数据池概况"""
    rel = reliable.get(lv, [])
    ref = reference.get(lv, [])

    print(f'\n=== L{lv} 数据池 ===')
    print(f'  可靠池: {len(rel)} 条 (bot={sum(1 for r in rel if r["source"]=="bot")} '
          f'summary={sum(1 for r in rel if r["source"]=="summary")} '
          f'phase2={sum(1 for r in rel if r["source"]=="phase2")})')
    print(f'  参考池: {len(ref)} 条 (phase1 + phase0)')

    if rel:
        print(f'\n  可靠池 (按 WR 降序):')
        print(f'  {"WR":>7} {"sd":>4} {"sc":>3} {"ratios":>25} {"of":>6} {"局数":>5} {"来源":>8} {"档位"}')
        print(f'  {"-"*70}')
        for r in sorted(rel, key=lambda x: -x['wr']):
            print(f'  {r["wr"]:>6.1f}% {r["sd"]:>4} {r["sc"]:>3} {r["ratios"]:>25} {r["of"]:>6} '
                  f'{r["totalGames"]:>5} {r["source"]:>8} {r.get("tier","")}')

    if ref:
        print(f'\n  参考池 (按 WR 降序，取前 10):')
        print(f'  {"WR":>7} {"sd":>4} {"sc":>3} {"ratios":>25} {"of":>6} {"局数":>5}')
        print(f'  {"-"*60}')
        for r in sorted(ref, key=lambda x: -x['wr'])[:10]:
            print(f'  {r["wr"]:>6.1f}% {r["sd"]:>4} {r["sc"]:>3} {r["ratios"]:>25} {r["of"]:>6} '
                  f'{r["totalGames"]:>5}')
        if len(ref) > 10:
            print(f'  ... 还有 {len(ref)-10} 条')


def print_summary_table(levels, reliable, reference):
    """打印所有关的汇总表"""
    print(f'\n{"关":>4} | {"可靠":>4} | {"bot":>4} | {"sum":>4} | {"ph2":>4} | {"参考":>4} | '
          f'{"WR范围":>14} | {"span":>6}')
    print('-' * 65)
    for lv in levels:
        rel = reliable.get(lv, [])
        ref = reference.get(lv, [])
        n_bot = sum(1 for r in rel if r['source'] == 'bot')
        n_sum = sum(1 for r in rel if r['source'] == 'summary')
        n_ph2 = sum(1 for r in rel if r['source'] == 'phase2')

        wrs = [r['wr'] for r in rel]
        if wrs:
            wr_range = f'{min(wrs):.1f}~{max(wrs):.1f}'
            span = max(wrs) - min(wrs)
        else:
            wr_range = '—'
            span = 0
        print(f'{lv:>4} | {len(rel):>4} | {n_bot:>4} | {n_sum:>4} | {n_ph2:>4} | '
              f'{len(ref):>4} | {wr_range:>14} | {span:>6.1f}')


def output_json_for_level(lv, reliable, reference):
    """输出单关 JSON 格式（去掉 _priority 等内部字段）"""
    rel = strip_meta(reliable.get(lv, []))
    ref = strip_meta(reference.get(lv, []))
    print(json.dumps({
        'level': int(lv),
        'updated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'reliable': sorted(rel, key=lambda x: -x['wr']),
        'reference': sorted(ref, key=lambda x: -x['wr']),
    }, ensure_ascii=False, indent=2))


# ==============================
# Main
# ==============================
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    spec = sys.argv[1]
    show_table = '--table' in sys.argv
    json_level = None
    min_games = None
    fmt = 'full'
    for i, a in enumerate(sys.argv):
        if a == '--json-lv' and i + 1 < len(sys.argv):
            json_level = sys.argv[i + 1]
        elif a.startswith('--min-games='):
            min_games = int(a.split('=')[1])
        elif a == '--raw':
            min_games = 1
        elif a == '--format=min':
            fmt = 'min'

    levels = parse_levels(spec)
    print(f'检索范围: {len(levels)} 关 ({levels[0]}-{levels[-1]})')

    # 读数据
    bot_data = read_bot_attempts(levels)
    opt_rel, opt_ref = read_opt_data(levels)

    # 合并 reliable
    reliable = defaultdict(list)
    for lv in levels:
        reliable[lv] = bot_data.get(lv, []) + opt_rel.get(lv, [])

    # 去重
    reliable, reference = dedup_pools(reliable, opt_ref)

    # 按 min_games 过滤
    if min_games is not None:
        for lv in list(reliable.keys()):
            reliable[lv] = [r for r in reliable[lv] if r['totalGames'] >= min_games]
        for lv in list(reference.keys()):
            reference[lv] = [r for r in reference[lv] if r['totalGames'] >= min_games]

    # 输出
    if json_level:
        if json_level in levels:
            output_json_for_level(json_level, reliable, reference)
        else:
            print(f'关卡 {json_level} 不在检索范围内')
    elif show_table:
        print_summary_table(levels, reliable, reference)
        # 打印各关明细
        for lv in levels:
            print_level_pool(lv, reliable, reference)
    else:
        # 默认：汇总 + 各关明细
        print_summary_table(levels, reliable, reference)
        if fmt != 'min':
            for lv in levels:
                print_level_pool(lv, reliable, reference)

    # 打印全局统计
    total_rel = sum(len(reliable.get(lv, [])) for lv in levels)
    total_ref = sum(len(reference.get(lv, [])) for lv in levels)
    print(f'\n========== 总计 ==========')
    print(f'  可靠池: {total_rel} 条')
    print(f'  参考池: {total_ref} 条')


if __name__ == '__main__':
    main()
