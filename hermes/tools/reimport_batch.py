#!/usr/bin/env python3
"""④ 入库批次全流程编排：重选 → 落盘(asset+Excel+board+LevelDatabase)。

把分散步骤串成一条命令（2026-08-05 用户要求"哪些步骤能脚本化"）：
  1. 重选最优档位（filter_verified，find_best_monotonic）
  2. 生成 reimport JSON（tools/reimport.py 消费）
  3. reimport.py 落盘（write_ddc + write_tiers + board + LevelDatabase）—— 用户确认后加 --apply
  4. gen_payload.py 生成 DB payload（只含落盘成功的关）
  5. leveldb_sync dryrun + write_level_db.mjs 写入（dryrun FAIL 阻断写入）

2026-08-05 审查修复（P1/P2）：
  A. reimport 部分关 FAIL → 中止，不写 DB（防旧 asset 配置入库）
  B. gen_payload 只含 build_config 成功的关（防未落盘关写 DB）
  C. dryrun FAIL → 阻断正式写入
  D. tmp JSON 带时间戳 + 完成后删除（防旧快照误用）
  E. 单关 try/except（某关异常跳过不中断批次）
  F. sys.executable 保证父子同解释器 + subprocess timeout

用法（分步，每次展示结果等确认）：
  # 只读：重选 + 生成 JSON（不写任何文件）
  python tools/reimport_batch.py --levels 158,174,180 --dry-run
  # 落盘 + DB（--apply 才写 asset/Excel/board/DB）
  python tools/reimport_batch.py --levels 158,174,180 --apply
  # 只落盘不写 DB
  python tools/reimport_batch.py --levels 158,174,180 --apply --no-db
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

from tools.data.adapters import excel_target as et
from tools.data.pool import get_all_records, dedup_records, filter_verified, find_best_monotonic

REIMPORT_JSON = os.path.join(HERMES, 'project-state', 'reimport_batch_tmp.json')
GEN_PAYLOAD = os.path.join(HERMES, 'tools', 'gen_payload.py')
REIMPORT = os.path.join(HERMES, 'tools', 'reimport.py')
LEVELDB = os.path.join(HERMES, 'tools', 'leveldb_sync')
CMD_TIMEOUT = 600  # 坑 112 教训：subprocess timeout > 实测最慢路径


def parse_levels(s):
    out = set()
    for part in str(s or '').split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-')
            try:
                out.update(range(int(a), int(b) + 1))
            except ValueError:
                print(f'⚠️ 非法关卡段: {part}')
                continue
        else:
            try:
                out.add(int(part))
            except ValueError:
                print(f'⚠️ 非法关卡: {part}')
                continue
    return sorted(out)


def build_config(lvs, note='重新入库 8-05', date='2026-08-05重录'):
    """重选最优 → reimport JSON（Normal 传 3 套，其余传 5 套）。单关异常跳过不中断（审查 E）。"""
    cfg = {}
    for lv in lvs:
        try:
            t = et.get_target(lv)
            if not t:
                print(f'L{lv}: 无目标配置，跳过')
                continue
            recs = dedup_records(get_all_records(str(lv)))
            ver = filter_verified(recs)
            res = find_best_monotonic(ver, t['tiers'], top_n=1, difficulty=t['diff'])
            if not res or not res[0]:
                print(f'L{lv}: 池子无组合，跳过')
                continue
            best = res[0][2]
            if t['diff'] == 'normal':
                idx = [0, 2, 4]  # Normal 只传 3 套，reimport 自动展开
            else:
                idx = [0, 1, 2, 3, 4]
            tiers = []
            for i in idx:
                r = best[i]
                tiers.append({
                    'wr': r['wr'],
                    'sd': int(r['sd']),
                    'sc': int(r['sc']),
                    'ratios': str(r['ratios']),
                    'of': float(r['of']),
                    'note': f"{r.get('source')} {r.get('totalGames', '?')}局",
                })
            cfg[str(lv)] = {
                'diff': t['diff'],
                'targets': [int(x) for x in t['tiers']],
                'date': date,
                'note': note,
                'tiers': tiers,
            }
            wrs = [r['wr'] for r in best]
            print(f'L{lv} [{t["diff"]}]: ' + ' / '.join(f'{w:.1f}' for w in wrs))
        except Exception as e:
            print(f'L{lv}: 异常跳过: {e}')
            continue
    return cfg


def run(cmd_list, cwd=None, check_stdout=None):
    """执行命令（列表参数，无 shell 注入；timeout 防挂起）。
    check_stdout: 若提供，stdout 含该字符串则视为失败（缺陷 C：dryrun FAIL 阻断）。
    """
    print(f'\n$ {" ".join(cmd_list)}')
    try:
        r = subprocess.run(cmd_list, cwd=cwd or HERMES, timeout=CMD_TIMEOUT,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        print(f'❌ 命令超时（>{CMD_TIMEOUT}s）: {" ".join(cmd_list)}')
        sys.exit(1)
    print(r.stdout)
    if r.stderr:
        print(r.stderr)
    if r.returncode != 0:
        print(f'❌ 命令失败: {" ".join(cmd_list)}')
        sys.exit(r.returncode)
    if check_stdout and check_stdout in r.stdout:
        print(f'❌ 检测到失败标记 "{check_stdout}"，中止')
        sys.exit(1)
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description='入库批次全流程（重选→落盘→DB）')
    ap.add_argument('--levels', required=True, help='关卡列表/区间')
    ap.add_argument('--dry-run', action='store_true', help='只重选+生成 JSON，不写任何文件')
    ap.add_argument('--apply', action='store_true', help='真正落盘（asset/Excel/board/DB）')
    ap.add_argument('--no-db', action='store_true', help='落盘但不写关卡数据库')
    ap.add_argument('--note', default='重新入库 8-05', help='Excel/board 备注')
    ap.add_argument('--date', default='2026-08-05重录', help='board 入库日期列')
    ap.add_argument('--source', default=None, help='DB sourceFileName（默认自动带时间戳）')
    args = ap.parse_args()

    # 缺陷 F（审查）：source 带批次标识，防同名混淆（坑 93 按 sourceFileName 验证）
    if args.source is None:
        args.source = f'hermes-import-{datetime.now().strftime("%Y%m%d-%H%M%S")}.csv'

    lvs = parse_levels(args.levels)
    print(f'=== 步骤1: 重选最优档位（{len(lvs)} 关）===')
    cfg = build_config(lvs, args.note, args.date)
    if not cfg:
        print('无可用组合，退出')
        sys.exit(1)

    # 缺陷 D（审查）：tmp JSON 带时间戳，防旧快照误用
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    tmp_json = os.path.join(HERMES, 'project-state', f'reimport_batch_{ts}.json')
    json.dump(cfg, open(tmp_json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n已生成 reimport JSON: {os.path.basename(tmp_json)}（{len(cfg)} 关）')

    if args.dry_run:
        print('\nDRY-RUN：展示 reimport 预览（不写任何文件）')
        run([sys.executable, 'tools/reimport.py', '--config', tmp_json, '--dry-run'])
        os.remove(tmp_json)
        print('\n完成（dry-run，未写任何文件，tmp 已清理）')
        return

    if not args.apply:
        print('\n未加 --apply：只生成了 JSON。确认无误后加 --apply 执行落盘。')
        print(f'JSON 路径: {tmp_json}（确认后删除或保留均可）')
        return

    # 落盘
    print('\n=== 步骤2: reimport 落盘（asset+Excel+board+LevelDatabase）===')
    out = run([sys.executable, 'tools/reimport.py', '--config', tmp_json])
    # 缺陷 A（审查 P1）：reimport 部分关 FAIL → 中止，不写 DB（防旧 asset 配置入库）
    if 'FAIL' in out or '失败' in out:
        print('❌ reimport 有关失败，中止（不写 DB）')
        sys.exit(1)
    # 缺陷 D：落盘成功后清理 tmp
    os.remove(tmp_json)

    if args.no_db:
        print('\n已跳过关卡数据库写入（--no-db）')
        return

    # 缺陷 B（审查 P1）：只含 build_config 成功的关（cfg.keys()），不是原始请求 lvs
    print('\n=== 步骤3: 生成 DB payload ===')
    lvs_str = ','.join(sorted(int(x) for x in cfg.keys()))
    run([sys.executable, 'tools/gen_payload.py', '--levels', lvs_str, '--source', args.source])

    print('\n=== 步骤4: DB dryrun ===')
    dry = run(['node', 'write_level_db_dryrun.mjs'], cwd=LEVELDB)
    # 缺陷 C（审查 P2）：dryrun 有失败标记 → 阻断正式写入
    if '失败' in dry and '失败 0' not in dry:
        print('❌ dryrun 有关失败，中止正式写入')
        sys.exit(1)

    print('\n=== 步骤5: DB 正式写入 ===')
    run(['node', 'write_level_db.mjs'], cwd=LEVELDB)
    print('\n✅ 全部完成')


if __name__ == '__main__':
    main()
