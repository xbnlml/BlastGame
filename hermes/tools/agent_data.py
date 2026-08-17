#!/usr/bin/env python3
"""Agent Data — 数据池管理 Agent（全自动）

职责：刷新 stage-data 数据池 + level_sig 关卡设计校验 + asset 完整性检查
安全：只写 stage-data/ 和 asset DDC 块，不删任何源数据，不执行 git
自愈：刷新失败自动重试一次，签名失败打 warn 不阻塞
"""
import argparse, json, os, sys, traceback, time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TOOLS_DIR))

from tools.asset_patcher import level_sig, verify_integrity
from tools.get_level_pool import parse_levels
from tools.dump_level_pools import build_level_pools, dump_all_pools

# ── 安全白名单：允许写入的路径前缀 ──
ALLOWED_WRITE_PREFIXES = [
    'stage-data', 'assets_backup',
    'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test/',
    'BlastGame', 'hermes',  # 允许在项目目录内运行
]
FORBIDDEN_CMDS = ['git ', 'rm -rf', 'del /', 'checkout', 'reset', 'clean', 'restore']


def _safe_check(path: str) -> bool:
    for prefix in ALLOWED_WRITE_PREFIXES:
        if prefix.replace('/', os.sep) in path.replace('/', os.sep):
            return True
    return False


def refresh_pools(levels):
    """刷新数据池，失败自动重试一次"""
    for attempt in range(2):
        try:
            reliable, reference = build_level_pools(levels)
            dump_all_pools(reliable, reference)
            total_rel = sum(len(v) for v in reliable.values())
            total_ref = sum(len(v) for v in reference.values())
            return {'ok': True, 'reliable': total_rel, 'reference': total_ref,
                    'levels': len([l for l in levels if l in reliable])}
        except Exception as e:
            if attempt == 0:
                time.sleep(3)
            else:
                return {'ok': False, 'error': str(e), 'attempts': attempt+1}


def verify_signatures(levels):
    results = []
    for lv_str in levels:
        try:
            lv = int(lv_str)
            sig = level_sig(lv)
            ok, msg = verify_integrity(lv)
            results.append({'level': lv, 'sig': sig, 'integrity_ok': ok, 'integrity_msg': msg})
        except Exception as e:
            results.append({'level': int(lv_str), 'sig': None, 'integrity_ok': False,
                           'integrity_msg': str(e)})
    return results


def main():
    parser = argparse.ArgumentParser(description='Agent Data — 刷新数据池')
    parser.add_argument('--levels', required=True)
    parser.add_argument('--output', choices=['json','text'], default='json')
    parser.add_argument('--no-refresh', action='store_true')
    args = parser.parse_args()

    # 安全检查：禁止写入非白名单路径
    cwd = os.getcwd()
    if not any(prefix in cwd.replace('/',os.sep) for prefix in ALLOWED_WRITE_PREFIXES):
        cwd_ok = any(prefix in __file__.replace('/',os.sep) for prefix in ALLOWED_WRITE_PREFIXES)
        if not cwd_ok:
            print(json.dumps({'action':'agent_data','status':'blocked','error':'cwd not in allowed paths'}), file=sys.stderr)
            sys.exit(1)

    levels = parse_levels(args.levels)

    pool = {}
    if not args.no_refresh:
        pool = refresh_pools(levels)
    sigs = verify_signatures(levels)

    report = {'action': 'agent_data', 'levels_processed': len(levels),
              'pool': pool, 'signatures': sigs,
              'status': 'ok' if pool.get('ok', True) else 'pool_error'}

    if args.output == 'json':
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    else:
        print(f'Pool: {pool.get("reliable",0)} rel, {pool.get("reference",0)} ref')
        for s in sigs:
            print(f'  L{s["level"]}: sig={s["sig"][:12] if s["sig"] else "None"} int={s["integrity_ok"]}')


if __name__ == '__main__':
    main()
