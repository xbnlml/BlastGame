#!/usr/bin/env python3
"""通过 Unity batch mode 提交并运行 bot 批跑（使用 Jenkins 官方入口）。

用法:
  python scripts/submit_batch_unity.py "56,57,71,86" --games 400
  python scripts/submit_batch_unity.py "70" --games 400 --tiers "1,2,3,4,5"
  python scripts/submit_batch_unity.py "56" --games 400 --tiers 3 --skip-patch
"""
import os, sys, time, subprocess, re

REPO = r'C:\Users\Administrator\Documents\BlastGame'
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools')
BOT_DIR = os.path.join(REPO, 'telemetry', 'bot')
UNITY_EXE = r'C:\Program Files\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe'

# Jenkins 官方入口（不用 request.json，用命令行参数）
EXECUTE_METHOD = "BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine"


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


def echo(m): print(m, flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Unity batch mode bot 批跑')
    parser.add_argument('levels', help='关卡范围')
    parser.add_argument('--games', type=int, default=400)
    parser.add_argument('--tiers', default='', help='要跑的档位（必填）')
    parser.add_argument('--skip-patch', action='store_true')
    parser.add_argument('--tag', default='')
    parser.add_argument('--dry-run', action='store_true', help='验证配置但不执行（检查 probe_configs + asset 完整性）')
    args = parser.parse_args()

    LEVELS = parse_levels(args.levels)
    tier_str = args.tiers
    run_count = args.games

    # ── 0. Dry-run：验证不执行 ──
    if args.dry_run:
        echo('=== DRY RUN: %d level(s) tiers=%s games=%d ===' % (len(LEVELS), tier_str, run_count))
        echo('    ' + ', '.join(LEVELS))
        sys.path.insert(0, TOOLS)
        import json as j
        with open(os.path.join(TOOLS, 'probe_configs.json')) as f:
            pc = j.load(f)
        ok = True
        for lv in LEVELS:
            cfg = pc.get(lv)
            if not cfg:
                echo('  !! L%s: no probe config in probe_configs.json' % lv)
                ok = False
                continue
            for i in range(1, 6):
                key = 'T%d' % i
                t = cfg.get(key)
                if not t:
                    echo('  !! L%s: missing %s' % (lv, key))
                    ok = False
                    continue
                n_vals = len(str(t.get('ratios','')).split(','))
                if n_vals != t.get('sc', 0):
                    echo('  !! L%s %s: sc=%d but ratios has %d values' % (lv, key, t.get('sc'), n_vals))
                    ok = False
        if ok:
            echo('  All probe configs: OK')
        # Asset integrity
        sys.path.insert(0, os.path.join(TOOLS, '..'))
        from tools.asset_patcher import verify_all
        all_ok, results = verify_all([int(lv) for lv in LEVELS])
        for lv, (ok2, msg) in sorted(results.items()):
            echo('  L%d: %s' % (lv, msg))
        if not all_ok:
            echo('  !! Some assets corrupt')
            ok = False
        if ok:
            echo('✅ DRY RUN PASSED — no changes made')
        else:
            echo('❌ DRY RUN FAILED — fix errors before real submit')
        sys.exit(0 if ok else 1)

    echo('=== BATCH MODE SUBMIT: %d level(s) tiers=%s games=%d ===' % (len(LEVELS), tier_str, run_count))
    echo('    ' + ', '.join(LEVELS))

    # 1. Patch assets
    if not args.skip_patch:
        sys.path.insert(0, TOOLS)
        import json as j
        with open(os.path.join(TOOLS, 'probe_configs.json')) as f:
            pc = j.load(f)
        sys.path.insert(0, os.path.join(TOOLS, '..'))
        from tools.asset_patcher import write_ddc
        for lv in LEVELS:
            cfg = pc.get(lv)
            if not cfg:
                echo('  !! No probe config for L%s, skipping' % lv)
                continue
            tiers = []
            for i in range(1, 6):
                key = 'T%d' % i
                if key in cfg:
                    tiers.append(cfg[key])
                else:
                    tiers.append({'sd': 0, 'sc': 5, 'ratios': '1,1,1,1,1', 'of': 0.5})
            write_ddc(int(lv), tiers)
            # 写后回读对比 probe_configs（防写入错误）
            from tools.asset_patcher import read_ddc as _rd
            _readback = _rd(int(lv))
            if not _readback:
                echo('  ❌ L%s: 写后 asset 读不出' % lv)
                sys.exit(1)
            _ok = True
            for _i in range(5):
                _key = 'T%d' % (_i + 1)
                _exp = cfg.get(_key) or {'sd': 0, 'sc': 5, 'ratios': '1,1,1,1,1', 'of': 0.5}
                _got = _readback[_i]
                for _f in ('sd', 'sc', 'ratios', 'of'):
                    if str(_exp.get(_f)) != str(_got.get(_f)):
                        echo('  ❌ L%s %s %s: 预期=%s asset=%s' % (lv, _key, _f, _exp.get(_f), _got.get(_f)))
                        _ok = False
            if not _ok:
                echo('  ❌ L%s: asset 写入内容与 probe_configs 不一致，终止提交' % lv)
                sys.exit(1)
        echo('  Patched %d assets' % len(LEVELS))
    else:
        echo('  --skip-patch: asset unchanged')

    # 2. 拼 Unity 命令行（使用 Jenkins 官方入口，无需 request.json）
    cmd = [
        UNITY_EXE,
        '-batchMode',
        '-nographics',
        '-projectPath', REPO,
        '-executeMethod', EXECUTE_METHOD,
        '-BlastBotBatchLevels', ','.join(LEVELS),
        '-BlastBotBatchRunCount', str(run_count),
        '-BlastBotBatchTiers', tier_str,
        '-BlastBotBatchLevelFolder', 'test',
        '-BlastBotBatchRecordReplay', 'false',
        '-BlastBotBatchDedupeEnabled', 'false',
        '-logFile', '-',  # 日志输出到 stdout，实时可见
        '-quit',
    ]
    echo('  Starting Unity...')

    # 3. 启动 Unity 并实时捕获输出
    timeout = max(len(LEVELS) * len(tier_str.split(',')) * 300, 7200)
    deadline = time.time() + timeout

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=REPO, bufsize=1, text=True, encoding='utf-8', errors='replace')

    completed = False
    while time.time() < deadline:
        # 读一行输出（非阻塞）
        line = proc.stdout.readline() if proc.stdout else ''
        if line:
            line = line.strip()
            # 实时输出进度，过滤掉噪声
            if 'Bot Batch' in line or 'BotCampaign' in line or '完成' in line or '结果' in line or 'error' in line.lower() or 'exception' in line.lower():
                echo('  [Unity] ' + line)
            # 检测完成标志
            if 'Bot Batch Jenkins' in line and '完成' in line:
                completed = True
        else:
            # 检查进程是否已退出
            ret = proc.poll()
            if ret is not None:
                echo('  Unity exited with code %d' % ret)
                break
            time.sleep(0.5)

    if not completed and proc.poll() is None:
        echo('  TIMEOUT: killing Unity')
        proc.kill()

    # 4. 读取剩余 stdout
    stdout, _ = proc.communicate(timeout=10) if proc.stdout else ('', '')
    # 查找完成标记
    for line in (stdout or '').split('\n'):
        if '完成' in line and '导出目录' in line:
            echo('  [Unity] ' + line.strip())

    # 5. 刷新池子
    dump_script = os.path.join(TOOLS, 'dump_level_pools.py')
    if os.path.exists(dump_script):
        subprocess.run([sys.executable, '-X', 'utf8', dump_script], capture_output=True)
        echo('  Pool refreshed')
    
    # 读取本次 batch 的新 CSV 数据
    if os.path.isdir(BOT_DIR):
        dirs = sorted(d for d in os.listdir(BOT_DIR) if not d.startswith('_'))
        if dirs:
            latest = dirs[-1]
            dp = os.path.join(BOT_DIR, latest)
            echo('  Batch dir: ' + latest)
            if os.path.isdir(dp):
                for td in sorted(os.listdir(dp)):
                    tdir = os.path.join(dp, td)
                    if not os.path.isdir(tdir): continue
                    m = re.search(r'T(\d+)', td)
                    if not m: continue
                    for sf in glob.glob(os.path.join(tdir, 'campaign-summary-*.csv')):
                        with open(sf, encoding='utf-8-sig') as fh:
                            for row in csv.DictReader(fh):
                                lv = row.get('level', '')
                                wr = row.get('winkate', '')
                                if lv in LEVELS and wr:
                                    echo('  L{} T{}: {:.1f}%'.format(lv, m.group(1), float(wr)*100))
    
    echo('=== DONE ===')
