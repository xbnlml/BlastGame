#!/usr/bin/env python3
"""统一入库落盘工具（2026-08-05 新建，坑 118 教训落地）。

入库 = 落盘三动作（用户定义：选数据/判定是上游流程，与入库无关）：
  ① write_ddc + verify_asset（写 asset）
  ② write_tiers（Excel 就地更新，用现有工具 project-state/_archive/write_excel.py）
  ③ board.md 行更新（固定 7 列整行替换，禁止内联正则重排）

用法：
  python tools/reimport.py --config <json> [--dry-run]

--config JSON 结构（每关一个条目，tiers 的 wr 是百分数，脚本转小数）：
{
  "151": {
    "diff": "hard",                          # normal/hard/superhard
    "targets": [70, 55, 40, 30, 20],
    "status": "✅已入库",
    "date": "2026-08-05重录",
    "note": "重新入库 8-05",
    "tiers": [
      {"wr": 75.3, "sd": 27, "sc": 3, "ratios": "2,0,8", "of": 0.67, "note": "bot 300局"},
      {"wr": 54.2, "sd": 31, "sc": 5, "ratios": "1,1,1,10,1", "of": 0.5, "note": "summary 400局"},
      ... 共 5 档
    ]
  }
}

Normal 关 tiers 只需传 3 套（T1,T3,T5）或 5 套都行——write_tiers 自动展开 T2=T1/T5=T4。
write_ddc 需要 5 档：Normal 自动展开（idx [0,0,2,4,4]），Hard/SH 用 [0,1,2,3,4]。

--dry-run：只打印将执行的动作，不写任何文件。
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

XL_PATH = os.path.join(HERMES, '手动挑配置记录.xlsx')
BOARD_PATH = os.path.join(HERMES, 'project-state', 'board.md')
WRITE_EXCEL = os.path.join(HERMES, 'project-state', '_archive', 'write_excel.py')


def _load_config(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _normal_expand_tiers(tiers, diff):
    """Normal 关 5 档展开（T2=T1, T5=T4）。tiers 可传 3 套或 5 套。"""
    if diff != 'normal':
        return tiers
    if len(tiers) == 5:
        return tiers
    if len(tiers) != 3:
        raise ValueError(f'Normal 关 tiers 应为 3 套（T1/T3/T5），收到 {len(tiers)}')
    t1, t3, t5 = tiers
    return [t1, dict(t1), t3, t5, dict(t5)]


def _update_board(lv, cfg, tiers5, dry_run):
    """board.md 固定 7 列整行替换（坑 118：不要泛化正则重排，整行显式写出）。
    tiers5 = 展开后的 5 档（Normal T1=T2/T4=T5 同值也显示 5 档原始 WR）。
    2026-08-07 加固：写前备份 board（审计 H7——之前只备份 Excel 不备份 board，
    写坏无法恢复）。"""
    if not os.path.exists(BOARD_PATH):
        raise FileNotFoundError(f'board 不存在: {BOARD_PATH}')
    if not dry_run:
        ts = datetime.now().strftime('%H%M%S')
        bak = BOARD_PATH.replace('.md', f'_before_reimport_{ts}.bak')
        shutil.copy2(BOARD_PATH, bak)
    with open(BOARD_PATH, encoding='utf-8') as f:
        lines = f.read().splitlines()

    targets_str = '/'.join(str(int(x)) for x in cfg['targets'])
    wrs = [t['wr'] for t in tiers5]
    wr_str = '/'.join(f'{w:.1f}' for w in wrs)
    diff = cfg['diff']
    status = cfg.get('status', '✅已入库')
    date = cfg.get('date', datetime.now().strftime('%Y-%m-%d'))
    note = cfg.get('note', '')

    new_line = f'| {lv} | {diff} | {status} | {date} | {targets_str} | {wr_str} | {note} |'

    found = False
    for i, line in enumerate(lines):
        # 只匹配行首关卡号（避免匹配到其他表）
        parts = line.split('|')
        if len(parts) >= 3 and parts[1].strip() == str(lv):
            old = line
            lines[i] = new_line
            found = True
            if dry_run:
                print(f'  [dry] board L{lv}:\n    -{old}\n    +{new_line}')
            else:
                print(f'  board L{lv} 已更新')
            break
    if not found:
        raise ValueError(f'board 中找不到 L{lv} 的行')

    if not dry_run:
        with open(BOARD_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return new_line


def _backup_excel(dry_run):
    if dry_run:
        print(f'  [dry] 备份 Excel → 手动挑配置记录_before_reimport_*.bak')
        return None
    ts = datetime.now().strftime('%H%M%S')
    bak = XL_PATH.replace('.xlsx', f'_before_reimport_{ts}.bak')
    shutil.copy2(XL_PATH, bak)
    print(f'  备份 Excel → {os.path.basename(bak)}')
    return bak


def _import_write_excel():
    """从 _archive 导入 write_tiers（现有工具，禁止内联重写）。
    注意：write_excel.py 的 XL_PATH = TOOL_DIR/../手动挑配置记录.xlsx 会算到
    project-state/ 下（工具所在目录的上一级）——必须覆盖为 hermes 根的正确路径。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location('write_excel', WRITE_EXCEL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.XL_PATH = XL_PATH  # 覆盖错误路径（2026-08-05 修复）
    return mod.write_tiers


def reimport(config, dry_run=False):
    """执行入库落盘。config = {lv: {diff, targets, tiers[], ...}}"""
    write_tiers = _import_write_excel()
    from tools.asset_patcher import write_ddc, verify_asset

    results = []
    for lv_str, cfg in sorted(config.items(), key=lambda x: int(x[0])):
        lv = int(lv_str)
        diff = cfg['diff']
        print(f'=== L{lv} [{diff}] ===')

        # ① asset（write_ddc + verify_asset）
        tiers5 = _normal_expand_tiers(cfg['tiers'], diff)
        if len(tiers5) != 5:
            raise ValueError(f'L{lv}: 展开后 tiers 应为 5 档，收到 {len(tiers5)}')
        if dry_run:
            print(f'  [dry] write_ddc L{lv} 5 档 (T1 sd={tiers5[0]["sd"]} ... T5 sd={tiers5[4]["sd"]})')
        else:
            ok, msg = write_ddc(lv, tiers5)
            if not ok:
                results.append((lv, 'FAIL', f'write_ddc: {msg}'))
                print(f'  ❌ write_ddc 失败: {msg}')
                continue
            vok, vmsg = verify_asset(lv, tiers5)
            if not vok:
                results.append((lv, 'FAIL', f'verify_asset: {vmsg}'))
                print(f'  ❌ verify_asset 失败: {vmsg}')
                continue
            print(f'  ✅ write_ddc + verify_asset OK')

        # ② Excel（write_tiers：wr 转小数！坑 115）
        # 备注 = cfg.note（如"重新入库 8-05"）+ tier 来源局数（坑 51：必须标来源+局数）
        excel_note_prefix = cfg.get('note', '')
        excel_tiers = []
        for t in tiers5:
            note_parts = []
            if excel_note_prefix:
                note_parts.append(excel_note_prefix)
            if t.get('note'):
                note_parts.append(str(t['note']))
            excel_tiers.append({
                'wr': round(t['wr'] / 100.0, 4),  # 百分数 → 小数
                'sd': int(t['sd']),
                'sc': int(t['sc']),
                'ratios': str(t['ratios']),
                'of': float(t.get('of', 0.5)),
                'note': ' '.join(note_parts),
            })
        if dry_run:
            wrs = [t['wr'] for t in tiers5]
            print(f'  [dry] write_tiers L{lv}: ' + ' / '.join(f'{w:.1f}' for w in wrs))
        else:
            ok, msg = write_tiers(lv, excel_tiers)
            if not ok:
                results.append((lv, 'FAIL', f'write_tiers: {msg}'))
                print(f'  ❌ write_tiers 失败: {msg}')
                continue
            print(f'  ✅ write_tiers OK')

        # ③ board（整行替换，用展开后的 5 档 WR）
        _update_board(lv, cfg, tiers5, dry_run)

        # ④ 关卡数据库同步（2026-08-10 用户要求：DB 同步纳入入库标准流程）
        #    用 gen_payload.py 生成 payload → node write_level_db.mjs 写入
        if not dry_run:
            db_ok = _sync_leveldb(lv, cfg, tiers5)
            if not db_ok:
                results.append((lv, 'OK', 'asset/Excel/board 完成，但 DB 同步失败（需手动 write_level_db.mjs）'))
                print(f'  ⚠ DB 同步失败——请手动 node tools/leveldb_sync/write_level_db.mjs')
            else:
                print(f'  ✅ LevelDatabase 同步完成')

        wrs = [t['wr'] for t in tiers5]
        results.append((lv, 'OK', ' / '.join(f'{w:.1f}' for w in wrs)))

    return results


def _sync_leveldb(lv, cfg, tiers5):
    """同步关卡数据库：生成 payload → 调 node write_level_db.mjs。
    返回 True/False。payload 存临时文件，写入后清理。"""
    import subprocess, tempfile, json as _json, os as _os
    wrs = [t['wr'] / 100.0 for t in tiers5]  # 百分数 → 小数
    ratios = []
    for t in tiers5:
        r = [int(x) for x in str(t['ratios']).replace('，', ',').split(',') if str(x).strip()]
        ratios.append(r)
    payload = {
        str(lv): {
            'tierConfigs': [
                {'startDifficulty': int(t['sd']), 'shuffleSplitCount': int(t['sc']),
                 'shuffleSplitRatios': ratios[i], 'shuffleOverflowFactor': float(t.get('of', 0.5))}
                for i, t in enumerate(tiers5)
            ],
            'tierWinRates': wrs,
            'importedAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'sourceFileName': f'reimport-{time.strftime("%Y%m%d")}-{lv}.json',
        }
    }
    payload_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'leveldb_sync', '_reimport_payload.json')
    with open(payload_path, 'w', encoding='utf-8') as f:
        _json.dump(payload, f, ensure_ascii=False)
    wl = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'leveldb_sync', 'write_level_db.mjs')
    r = subprocess.run(['node', wl], capture_output=True, text=True, encoding='utf-8', timeout=120)
    try:
        _os.remove(payload_path)
    except OSError:
        pass
    # 2026-08-10 P0 修复：不能只看 node 退出码（write_level_db 输出
    # "部分验证失败" 时退出码仍 0，导致 DB 漏写被当成成功——L163 案例）。
    # 必须回读 test.json 确认该关 reimport entry 存在且 winRate 匹配。
    if r.returncode != 0:
        return False
    try:
        run_path = _os.path.join(_os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame'),
                                 'LevelDatabase', 'Run', 'test.json')
        db = _json.load(open(run_path, encoding='utf-8'))
        entries = db.get('levels', {}).get(str(lv), {}).get('entries', [])
        src_name = f'reimport-{time.strftime("%Y%m%d")}-{lv}.json'
        new_entries = [e for e in entries if src_name in str(e.get('sourceFileName', ''))]
        if not new_entries:
            return False
        # 逐档确认 dealConfig 匹配（normal 同配置 dedup 后至少 3 条）
        def _norm(x):
            return ','.join(str(v).strip() for v in str(x).replace('，', ',').split(',') if str(v).strip())
        matched = 0
        for i, t in enumerate(tiers5):
            sd, sc, rat, of = int(t['sd']), int(t['sc']), _norm(t['ratios']), float(t.get('of', 0.5))
            for e in new_entries:
                dc = e.get('dealConfig', {})
                if (int(dc.get('startDifficulty', -1)) == sd
                        and int(dc.get('shuffleSplitCount', -1)) == sc
                        and _norm(dc.get('shuffleSplitRatios')) == rat
                        and abs(float(dc.get('shuffleOverflowFactor', -1)) - of) < 1e-6
                        and e.get('winRate') is not None):
                    matched += 1
                    break
        # 5 档配置应至少匹配 3 条（normal T1=T2/T4=T5 同配置 dedup）
        return matched >= 3
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description='统一入库落盘（asset+Excel+board）')
    ap.add_argument('--config', required=True, help='JSON 配置文件路径')
    ap.add_argument('--dry-run', action='store_true', help='只打印不写文件')
    args = ap.parse_args()

    config = _load_config(args.config)
    print(f'读取配置: {len(config)} 关')
    if args.dry_run:
        print('DRY-RUN 模式（不写任何文件）')
    else:
        _backup_excel(dry_run=False)

    results = reimport(config, dry_run=args.dry_run)

    print()
    print('=== 结果 ===')
    for lv, status, detail in results:
        print(f'L{lv}: {status} {detail}')

    if not args.dry_run:
        ok_count = sum(1 for _, s, _ in results if s == 'OK')
        print(f'完成 {ok_count}/{len(results)} 关。备份：手动挑配置记录_before_reimport_*.bak')
        # 入库后自动验证 asset↔DB 一致性（2026-08-10 规范化：不再手写验证脚本）
        if ok_count > 0:
            lvs = ','.join(str(lv) for lv, s, _ in results if s == 'OK')
            print(f'\n=== 入库后一致性验证（verify_asset_db_match）===')
            import subprocess, sys as _sys
            r = subprocess.run([_sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_asset_db_match.py'),
                                '--levels', lvs], capture_output=True, text=True, encoding='utf-8')
            print(r.stdout.strip())
            if r.returncode != 0:
                print('⚠ 一致性验证发现问题——asset 与 DB 有不匹配，请检查！')
            else:
                print('✅ 一致性验证通过：asset 参数 = DB 胜率对应参数')


if __name__ == '__main__':
    main()
