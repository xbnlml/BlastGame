"""对比关卡数据库 Run 胜率 vs 我们池子胜率（只读，不写任何文件）

逻辑：
1. asset 配置以我们为准（read_ddc）
2. 用 asset 的 boardFingerprint（官方 node 算）过滤 DB entry——只匹配当前 asset 牌面的 entry
3. 每档 dealConfig 匹配 asset 各档 → DB 胜率（单档 entry 结构）
4. 用 asset 每档配置在池子找同配置 verified 记录 → 我们的胜率
5. 输出对比表

用法：python tools/compare_level_db.py [--levels 151,152,153]（默认全扫 1-200）
"""
import sys, json, subprocess, argparse, os
sys.path.insert(0, r'D:\download\BlastGame\hermes')
sys.path.insert(0, r'D:\download\BlastGame\hermes\tools')

from tools.asset_patcher import read_ddc
from tools.data.pool import get_all_records, dedup_records

RUN_PATH = r'C:\Users\Administrator\Documents\BlastGame\LevelDatabase\Run\test.json'
ASSET_ROOT = r'C:\Users\Administrator\Documents\BlastGame\Assets\GameModule\GameMain\ConfigSo\Generated_enum'
FP_HELPER = r'D:\download\BlastGame\hermes\tools\leveldb_sync\get_asset_board_fp.mjs'

def norm_ratios(r):
    """归一化 ratios：DB 存数组 [10,1,1,1,10]，asset/池子存字符串 '10,1,1,1,10'。"""
    if r is None:
        return []
    if isinstance(r, str):
        return [int(x) for x in r.strip().replace('，', ',').split(',') if x.strip()]
    return [int(x) for x in r]

def config_key(c):
    sd = str(c.get('sd', '')).strip()
    sc = str(c.get('sc', '')).strip()
    ratios = ','.join(str(x) for x in norm_ratios(c.get('ratios'))).strip()
    try:
        of = float(c.get('of', 0) or 0)
    except (ValueError, TypeError):
        of = 0.0
    return (sd, sc, ratios, of)

def deal_key(dc):
    """单档 dealConfig → (sd, sc, ratios, of_float) 归一化（DB entry 用）。
    of 转 float 用于容差比较（DB 存 '0.500'，asset 存 0.5 或 '0.5'）。"""
    sd = str(dc.get('startDifficulty', '')).strip()
    sc = str(dc.get('shuffleSplitCount', '')).strip()
    ratios = ','.join(str(x) for x in norm_ratios(dc.get('shuffleSplitRatios'))).strip()
    try:
        of = float(dc.get('shuffleOverflowFactor', 0) or 0)
    except (ValueError, TypeError):
        of = 0.0
    return (sd, sc, ratios, of)

def find_asset_path(lv):
    """按 test/分段 找 asset（真实分段 1_20/21_40/41_60/.../181_200），兜底 os.walk。"""
    n = int(lv)
    if n <= 20: seg = '1_20'
    elif n <= 40: seg = '21_40'
    elif n <= 60: seg = '41_60'
    elif n <= 80: seg = '61_80'
    elif n <= 100: seg = '81_100'
    elif n <= 120: seg = '101_120'
    elif n <= 140: seg = '121_140'
    elif n <= 160: seg = '141_160'
    elif n <= 180: seg = '161_180'
    else: seg = '181_200'
    for group in ['test', 'funnel_b']:
        p = os.path.join(ASSET_ROOT, group, seg, f'{lv}.asset')
        if os.path.exists(p):
            return p
    # 兜底 walk Assets 找
    import pathlib
    root = r'C:\Users\Administrator\Documents\BlastGame\Assets'
    for dirpath, dirs, files in os.walk(root):
        if f'{lv}.asset' in files:
            return os.path.join(dirpath, f'{lv}.asset')
    return None

def get_board_fp(asset_path):
    """用官方 node 算 asset boardFingerprint。成功返回指纹字符串，失败返回 None。"""
    try:
        r = subprocess.run(['node', FP_HELPER, asset_path],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
        return data.get('boardFingerprint') if data.get('ok') else None
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser(description='对比关卡数据库 vs 池子胜率（只读）')
    parser.add_argument('--levels', help='要扫描的关卡逗号分隔，如 151,152；默认全扫 1-200')
    args = parser.parse_args()

    run = json.load(open(RUN_PATH, encoding='utf-8'))
    levels = run.get('levels', {})

    if args.levels:
        scan = [int(x) for x in args.levels.split(',') if x.strip()]
    else:
        scan = list(range(1, 201))

    print(f"{'关':>4} {'难度':<9} {'DB胜率(活动entry)':<32} {'我们池子(同配置)':<32} 结论")
    print('-' * 110)

    for lv in scan:
        key = str(lv)
        try:
            asset = read_ddc(lv)
        except Exception as e:
            print(f'{lv:>4}  asset读取失败: {e}')
            continue
        if not asset:
            print(f'{lv:>4}  无asset')
            continue
        try:
            from tools.data.adapters import excel_target as et
            _t = et.get_target(lv)
            diff_s = _t['diff'] if _t else '±'
        except Exception:
            diff_s = '±'

        # 池子数据
        recs = dedup_records(get_all_records(key))
        verified = [r for r in recs if r.get('source') in ('bot', 'summary', 'phase0')]

        # asset 每档配置 → 找同配置池子记录
        our_wrs = []
        for cfg in asset:
            k = config_key(cfg)
            match = None
            for r in verified:
                rk = config_key(r)
                if rk[0] == k[0] and rk[1] == k[1] and rk[2] == k[2]:
                    try:
                        if abs(float(rk[3] or 0) - float(k[3] or 0)) < 1e-6:
                            match = r
                            break
                    except ValueError:
                        continue
            if match:
                our_wrs.append((match['wr'], match.get('source', '?'), match.get('totalGames', 0)))
            else:
                our_wrs.append(None)

        # DB 活动 entry：按 boardFingerprint 过滤 + 单档 dealConfig 匹配
        db_wrs = None
        node = levels.get(key)
        if node and node.get('entries'):
            bf = get_board_fp(find_asset_path(lv)) if find_asset_path(lv) else None
            # bf 计算失败时退回：不按 bf 过滤（兼容旧 DB 无 bf 的 entry）
            cur_entries = node['entries']
            if bf:
                cur_entries = [e for e in cur_entries if e.get('boardFingerprint') == bf]
            # 每档 asset 配置 → 匹配单档 entry 的 dealConfig
            db_wrs = []
            for cfg in asset:
                k = config_key(cfg)
                found = None
                for e in cur_entries:
                    dc = e.get('dealConfig')
                    if not dc:
                        continue
                    if deal_key(dc) == k:
                        found = e.get('winRate')
                        break
                db_wrs.append(found)
            # 若全白（无匹配）→ 视为无活动 entry
            if all(w is None for w in db_wrs):
                db_wrs = None

        db_str = '无活动entry' if db_wrs is None else ','.join(
            f'{int(w*100)}%' if w is not None else '—' for w in db_wrs)
        our_str = ','.join(f'{int(w[0])}%' if w else '—' for w in our_wrs)

        # 结论
        if db_wrs is None:
            conclusion = '⚠️ 需写入(DB无此配置)'
        else:
            diff_cnt = 0
            for i in range(5):
                if our_wrs[i] and db_wrs[i] is not None:
                    if abs(our_wrs[i][0] - db_wrs[i] * 100) > 3:
                        diff_cnt += 1
            if diff_cnt >= 2:
                conclusion = f'🔄 {diff_cnt}档差>3pp,可对比'
            else:
                conclusion = '✅ 基本一致'

        print(f'{lv:>4} {diff_s:<9} {db_str:<32} {our_str:<32} {conclusion}')

if __name__ == '__main__':
    main()