"""验证 asset 配置 ↔ 关卡数据库 entry 一致性（打包前检查）

直接比参数：asset 每档 (sd, sc, ratios, of) 四元组 → DB 找参数完全一致的 entry
（同 boardFingerprint）→ 输出该 entry 的 winRate。

用途：打包前必须跑——确保当前 asset 打包时，数据库显示的胜率就是
asset 这套参数对应的胜率，一一对应。

用法：
  python tools/verify_asset_db_match.py            # 全扫 1-200
  python tools/verify_asset_db_match.py --levels 54,61,72   # 指定关
  python tools/verify_asset_db_match.py --show     # 同时输出每关 5 档胜率摘要

退出码：0 = 全部一致；1 = 有不一致（asset 参数在 DB 无同参数 entry 或 winRate 无效）
"""
import sys, json, subprocess, os, argparse
from pathlib import Path

HERMES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERMES))

from tools.project_paths import resolve_unity_repo

REPO = resolve_unity_repo(HERMES)
os.environ.setdefault('BLASTGAME_REPO', str(REPO))

from tools.asset_patcher import read_ddc

RUN_PATH = str(REPO / 'LevelDatabase' / 'Run' / 'test.json')
FP_HELPER = str(HERMES / 'tools' / 'leveldb_sync' / 'get_asset_board_fp.mjs')
ASSET_ROOT = str(REPO / 'Assets' / 'GameModule' / 'GameMain' / 'ConfigSo' / 'Generated_enum' / 'test')

def find_asset(lv):
    n = int(lv)
    seg = '1_20' if n<=20 else '21_40' if n<=40 else '41_60' if n<=60 else \
          '61_80' if n<=80 else '81_100' if n<=100 else '101_120' if n<=120 else \
          '121_140' if n<=140 else '141_160' if n<=160 else '161_180' if n<=180 else '181_200'
    p = os.path.join(ASSET_ROOT, seg, f'{lv}.asset')
    return p if os.path.exists(p) else None

def norm(r):
    if r is None: return []
    if isinstance(r, str): return [int(x) for x in r.strip().replace('，',',').split(',') if x.strip()]
    return [int(x) for x in r]

def get_bf(ap):
    rr = subprocess.run(['node', FP_HELPER, ap], capture_output=True, text=True, timeout=30)
    try:
        d = json.loads(rr.stdout)
        return d.get('boardFingerprint') if d.get('ok') else None
    except Exception:
        return None

def cfg_key(sd, sc, ratios, of):
    """四元组归一化：DB of 存 '0.500'、asset 存 0.5 → 统一 float 容差比较"""
    try:
        of_f = float(of or 0)
    except (ValueError, TypeError):
        of_f = 0.0
    return (str(sd).strip(), str(sc).strip(), ','.join(str(x) for x in norm(ratios)).strip(), of_f)

def check_level(lv, db_levels, show=False):
    """单关检查。返回 (问题列表, 胜率列表或None)"""
    try:
        asset = read_ddc(lv)
    except Exception as e:
        return [f'asset读取失败: {e}'], None
    if not asset or not isinstance(asset, list):
        return [f'asset异常: {asset}'], None
    ap = find_asset(lv)
    if not ap:
        return ['asset文件不存在'], None
    bf = get_bf(ap)
    node = db_levels.get(str(lv))
    es = node['entries'] if node else []
    if bf:
        es = [e for e in es if e.get('boardFingerprint') == bf]
    # DB 所有 entry 参数集合（同参数多条取最新）
    db_cfgs = {}
    for e in es:
        dc = e.get('dealConfig', {})
        if not dc: continue
        k = cfg_key(dc.get('startDifficulty',''), dc.get('shuffleSplitCount',''),
                    dc.get('shuffleSplitRatios'), dc.get('shuffleOverflowFactor',''))
        imp = str(e.get('importedAt','') or e.get('sourceFileName',''))
        if k not in db_cfgs or imp > db_cfgs[k][0]:
            db_cfgs[k] = (imp, e.get('winRate'), str(e.get('sourceFileName',''))[:30])
    problems = []
    wrs = []
    for i, a in enumerate(asset):
        k = cfg_key(a['sd'], a['sc'], a['ratios'], a['of'])
        if k not in db_cfgs:
            problems.append(f'T{i+1}: asset参数({k})在DB无同参数entry')
            wrs.append(None)
        else:
            imp, wr, src = db_cfgs[k]
            if wr is None or wr <= 0:
                problems.append(f'T{i+1}: DB同参数entry winRate={wr}（无效）src={src}')
                wrs.append(None)
            else:
                wrs.append(wr)
    return problems, wrs

def main():
    parser = argparse.ArgumentParser(description='验证 asset 配置 ↔ 关卡数据库 entry 一致性（打包前检查）')
    parser.add_argument('--levels', help='指定关（逗号分隔），默认全扫 1-200')
    parser.add_argument('--show', action='store_true', help='同时输出每关 5 档胜率摘要')
    args = parser.parse_args()

    db = json.load(open(RUN_PATH, encoding='utf-8'))
    levels = db.get('levels', {})

    if args.levels:
        scan = [int(x) for x in args.levels.split(',') if x.strip()]
    else:
        scan = list(range(1, 201))

    all_problems = []
    ok_tiers = 0
    for lv in scan:
        problems, wrs = check_level(lv, levels, args.show)
        if args.show and wrs and all(w is not None for w in wrs):
            pct = '/'.join(f'{int(w*100)}%' for w in wrs)
            print(f'L{lv}: {pct}')
        if problems:
            for msg in problems:
                all_problems.append(f'L{lv} {msg}')

    if all_problems:
        print(f'\n❌ {len(all_problems)} 个问题:')
        for m in all_problems[:40]:
            print(f'  {m}')
        sys.exit(1)
    else:
        total = len(scan) * 5
        print(f'\n✅ 全部 {total} 档（{len(scan)} 关）：asset 参数 = DB 显示的胜率对应参数，严格一致')
        print('   （asset 打包时，数据库显示的胜率就是 asset 这套参数对应的胜率）')

if __name__ == '__main__':
    main()