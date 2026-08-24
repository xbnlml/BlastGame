#!/usr/bin/env python3
"""批量跑 bot——只跑，不碰 asset 配置。

用法:
  python scripts/submit_batch_unity.py "172" --tiers "1,3,5"
  python scripts/submit_batch_unity.py "170-185" --tiers "1,2,3,4,5" --games 400

局数标准（2026-08-10）:
  探针批（筛选方向）: --games 200 --adaptive-stop   # 200 局足够看出方向
  验证批（入库前）:   --games 400                    # 400 局精测，跑满

Asset 配置请通过 write_ddc 或 apply_probes.py 单独管理。
"""

import csv, glob, json, os, re, subprocess, sys, time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERMES = os.path.dirname(SCRIPT_DIR)
TOOLS = os.path.join(HERMES, 'tools')
SCRIPTS = SCRIPT_DIR
BATCH_LOG_DIR = os.path.join(HERMES, 'batch-logs')

def _find_unity_exe():
    """从 ProjectSettings/ProjectVersion.txt 读取版本，拼 Hub 路径。"""
    pv_file = os.path.join(
        os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame'),
        'ProjectSettings', 'ProjectVersion.txt')
    try:
        with open(pv_file, encoding='utf-8') as f:
            for line in f:
                if 'm_EditorVersion:' in line:
                    ver = line.split(':', 1)[1].strip()
                    exe = os.path.expandvars(
                        r'%ProgramFiles%\Unity\Hub\Editor\{0}\Editor\Unity.exe'.format(ver))
                    if os.path.exists(exe):
                        return exe
    except OSError:
        pass
    return r'%ProgramFiles%\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe'


UNITY_EXE = _find_unity_exe()
REPO = os.environ.get('BLASTGAME_REPO',
    r'C:\Users\Administrator\Documents\BlastGame')
BOT_DIR = os.path.join(REPO, 'telemetry', 'bot')

EXECUTE_METHOD = 'BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine'


def echo(s):
    print(s, flush=True)


def eprint(s, end='\n'):
    print(s, end=end, flush=True)


def parse_levels(spec):
    levels = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            levels.update(range(int(a), int(b) + 1))
        else:
            levels.add(int(part))
    return sorted(levels)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Unity batch mode bot 批跑')
    parser.add_argument('levels', help='关卡范围')
    parser.add_argument('--games', type=int, default=400)
    parser.add_argument('--tiers', default='', help='要跑的档位（必填）')
    parser.add_argument('--tag', default='')
    parser.add_argument('--strategy', default='scoring_opt_vg',
                        choices=['visible_greedy', 'scoring_opt_vg'],
                        help="Bot 策略（默认 scoring_opt_vg）")
    parser.add_argument('--yes', action='store_true',
                        help='跳过确认，直接执行')
    parser.add_argument('--dry-run', action='store_true',
                        help='验证 asset 完整性但不执行')
    parser.add_argument('--adaptive-stop', action='store_true',
                        help='开启贝叶斯自适应提前停止（默认关闭=跑满局数）')
    parser.add_argument('--worker-count', type=int, default=0,
                        help='Unity bot 并发 worker 数（0=用 EditorPrefs 默认4，建议 7 用满8核）')
    parser.add_argument('--bayes-min-runs', type=int, default=0,
                        help='贝叶斯提前停最小局数兜底（防极端配置过早停）')
    parser.add_argument('--skip-agent-pipeline', action='store_true',
                        help='跳过步骤4-6：agent_data/agent_analyze/agent_review（auto_loop 统筹时使用）')
    parser.add_argument('--v3-request', default='',
                        help='V3 request JSON：启用显式 run/attempt/batch identity 与 receipt 验收')
    args = parser.parse_args()

    LEVELS = parse_levels(args.levels)
    tier_str = args.tiers
    run_count = args.games
    v3_request = None
    if args.v3_request:
        try:
            with open(args.v3_request, encoding='utf-8') as _v3_f:
                v3_request = json.load(_v3_f)
            required_v3 = ('run_id', 'attempt_id', 'batch_id', 'request_plan_hash',
                           'executed_plan_hash', 'logic_version', 'expected_artifacts')
            missing_v3 = [k for k in required_v3 if not v3_request.get(k)]
            if missing_v3:
                raise ValueError('missing request fields: ' + ','.join(missing_v3))
            if v3_request['request_plan_hash'] != v3_request['executed_plan_hash']:
                raise ValueError('request/executed plan hash mismatch')
            if sorted(int(x) for x in v3_request.get('levels', [])) != LEVELS:
                raise ValueError('request levels differ from CLI levels')
            if sorted(int(x) for x in v3_request.get('tiers', [])) != sorted(
                    int(x) for x in tier_str.split(',') if x.strip()):
                raise ValueError('request tiers differ from CLI tiers')
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            echo('❌ V3 request invalid: ' + str(exc))
            sys.exit(2)

    if not args.yes:
        echo('=== 即将提交 ===')
        echo('  关卡: ' + ', '.join(str(l) for l in LEVELS))
        echo('  档位: %s' % tier_str)
        echo('  策略: %s' % args.strategy)
        echo('  每档: %d 局' % run_count)
        echo('')
        eprint('加 --yes 跳过此确认。继续？(y/N) ')
        try:
            resp = input().strip().lower()
        except EOFError:
            resp = 'n'
        if resp not in ('y', 'yes'):
            echo('已取消')
            sys.exit(0)

    # ── 0a. 提交前验证 asset 完整性 ──
    sys.path.insert(0, TOOLS)
    sys.path.insert(0, os.path.join(TOOLS, '..'))
    from tools.asset_patcher import verify_all, read_ddc
    fails = verify_all([int(lv) for lv in LEVELS])
    if fails:
        for lv, msg in fails:
            echo('  L%d: %s' % (lv, msg))
        echo('❌ asset 校验不通过，终止提交')
        sys.exit(1)
    echo('  asset 校验: %d/%d 通过' % (len(LEVELS) - len(fails), len(LEVELS)))

    # ── 0. Dry-run：只验证不执行 ──
    if args.dry_run:
        echo('=== DRY RUN: %d level(s) tiers=%s games=%d ===' %
             (len(LEVELS), tier_str, run_count))
        echo('    ' + ', '.join(str(l) for l in LEVELS))
        sys.path.insert(0, TOOLS)
        sys.path.insert(0, os.path.join(TOOLS, '..'))
        ok = True
        from tools.asset_patcher import verify_all
        fails = verify_all([int(lv) for lv in LEVELS])
        for lv, msg in fails:
            echo('  L%d: %s' % (lv, msg))
        if fails:
            echo('  !! Some assets corrupt')
            ok = False
        if ok:
            echo('✅ DRY RUN PASSED — no changes made')
        else:
            echo('❌ DRY RUN FAILED — fix errors before real submit')
        sys.exit(0 if ok else 1)

    echo('=== BATCH MODE SUBMIT: %d level(s) tiers=%s games=%d ===' %
         (len(LEVELS), tier_str, run_count))
    echo('    ' + ', '.join(str(l) for l in LEVELS))

    # 1. 拼 Unity 命令行
    cmd = [
        UNITY_EXE,
        '-batchMode',
        '-nographics',
        '-projectPath', REPO,
        '-executeMethod', EXECUTE_METHOD,
        '-BlastBotBatchLevels', ','.join(str(l) for l in LEVELS),
        '-BlastBotBatchRunCount', str(run_count),
        '-BlastBotBatchTiers', tier_str,
        '-BlastBotBatchLevelFolder', 'test',
        '-BlastBotBatchRecordReplay', 'false',
        '-BlastBotBatchDedupeEnabled', 'false',
        '-BlastBotBatchStrategy', args.strategy,
        *(['-BlastBotV3RunId', str(v3_request['run_id']),
           '-BlastBotV3AttemptId', str(v3_request['attempt_id']),
           '-BlastBotV3BatchId', str(v3_request['batch_id']),
           '-BlastBotV3RequestPlanHash', str(v3_request['request_plan_hash'])]
          if v3_request else []),
                '-BlastBotBatchAdaptiveStop', 'true' if args.adaptive_stop else 'false',
                '-BlastBotBatchBayesStdThreshold', '0.025',
                '-BlastBotBatchBayesBatchSize', '10',
                '-BlastBotBatchMinRuns', str(args.bayes_min_runs),
                '-BlastBotBatchWorkerCount', str(args.worker_count),
        '-logFile', '-',
        '-quit',
    ]
    echo('  Strategy: %s' % args.strategy)

    # ── 2. 启动 Unity（stdout 全程 tee 落盘，防异常丢失）──
    # 2026-08-14 事故：-logFile - 让 Unity 日志只进管道内存，批跑失败/被吞后
    # 事后无日志可查。现在每行同时写入 hermes/batch-logs/，异常可事后排查。
    os.makedirs(BATCH_LOG_DIR, exist_ok=True)
    log_path = os.path.join(
        BATCH_LOG_DIR,
        'unity_%s_%dL%s.log' % (datetime.now().strftime('%Y%m%d_%H%M%S'),
                                len(LEVELS), re.sub(r'[^\d,]', '', tier_str)))
    log_fh = open(log_path, 'w', encoding='utf-8', errors='replace')
    def tee(line):
        """写一行到批跑日志（flush 保证 kill/崩溃时已落盘）。"""
        log_fh.write(line + '\n')
        log_fh.flush()
    echo('  Unity 日志落盘: %s' % log_path)

    timeout = max(len(LEVELS) * len(tier_str.split(',')) * 300, 7200)
    deadline = time.time() + timeout

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=REPO, bufsize=1, text=True, encoding='utf-8',
                            errors='replace')

    completed = False
    fatal_reason = None
    seen_export_dir = ''   # 主循环里捕获的导出目录（修复 communicate 空返回导致丢失）
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ''
        if line:
            line = line.strip()
            tee(line)   # ← 落盘
            if any(k in line for k in ['Bot Batch', 'BotCampaign', '完成', '结果',
                                        'error', 'exception', 'Fatal']):
                echo('  [Unity] ' + line)
            # 2026-08-10 P1b：结构化捕获 Unity 失败原因（另一个实例占用/致命错误）
            if 'Fatal Error!' in line or 'Aborting batchmode' in line:
                if 'another Unity instance' in line or 'another instance' in line:
                    fatal_reason = 'unity_conflict'
                else:
                    fatal_reason = 'unity_fatal_error'
            if 'Bot Batch Jenkins' in line and '完成' in line:
                completed = True
            # 导出目录行在循环内就捕获（否则 communicate 返回空，current_batch 恒为空）
            if ('导出目录' in line or '最后导出目录' in line) and 'bot' in line:
                m = re.search(r'bot[/\\]([^/\\]+)$', line.strip().replace('\\', '/'))
                if m:
                    seen_export_dir = m.group(1)
        else:
            ret = proc.poll()
            if ret is not None:
                echo('  Unity exited with code %d' % ret)
                if ret != 0 and fatal_reason is None:
                    # 非零退出但没有 Fatal 标记 → 通用失败
                    fatal_reason = 'unity_exit_%d' % ret
                break
            time.sleep(0.5)

    if not completed and proc.poll() is None:
        echo('  TIMEOUT: killing Unity')
        proc.kill()
        fatal_reason = fatal_reason or 'unity_timeout'

    # 3. 读取剩余 stdout，获取 batch 目录（正常退出时 communicate 返回空——用循环内捕获的）
    # V3 never trusts a log line/mtime to select the batch. Unity must have
    # written the explicitly requested root; legacy mode keeps old discovery
    # solely for backwards-compatible non-V3 CLI calls.
    current_batch = str(v3_request['batch_id']) if v3_request else seen_export_dir
    stdout, _ = proc.communicate(timeout=10) if proc.stdout else ('', '')
    for line in (stdout or '').split('\n'):
        if line.strip():
            tee(line.strip())
        if not v3_request and '完成' in line and '导出目录' in line:
            m = re.search(r'bot[/\\]([^/\\]+)$', line.strip().replace('\\', '/'))
            if m:
                current_batch = m.group(1)
                echo('  Batch dir: ' + current_batch)
        elif '[Bot Batch Jenkins]' in line:
            echo('  [Unity] ' + line.strip())
    if current_batch:
        echo('  Batch dir: ' + current_batch)
    log_fh.close()

    # ── 3.5 导出验证（2026-08-14 事故防线）：每档必须有 campaign-summary CSV ──
    # 异常症状：每档 2 个时间戳子目录（导出抛异常被 catch 重导一次）+ 无 CSV。
    # 只靠池子时间核对太晚——这里在批跑结束立即检查，缺 CSV 直接报结构化失败。
    export_issues = []
    if current_batch:
        bp = os.path.join(BOT_DIR, current_batch)
        if os.path.isdir(bp):
            tiers_to_check = [t for t in tier_str.split(',') if t.strip()]
            for t in tiers_to_check:
                tdirs = [d for d in os.listdir(bp)
                         if re.match(r'^.*-T%s(-|$)' % t, d)]
                if not tdirs:
                    export_issues.append('T%s: 无批次子目录' % t)
                    continue
                csvs = []
                for td in tdirs:
                    td_path = os.path.join(bp, td)
                    if os.path.isdir(td_path):
                        csvs.extend(glob.glob(
                            os.path.join(td_path, 'campaign-summary-*.csv')))
                if not csvs:
                    export_issues.append(
                        'T%s: %d 个子目录但无 campaign-summary CSV (%s)'
                        % (t, len(tdirs), ' / '.join(tdirs)))
            if not export_issues:
                echo('  ✅ 导出验证: %d 档全部有 campaign-summary CSV' % len(tiers_to_check))
            else:
                echo('  ❌ 导出验证失败:')
                for e in export_issues:
                    echo('     - ' + e)
                echo('     → 查 Unity 日志: %s' % log_path)
        else:
            export_issues.append('batch 目录不存在: %s' % bp)
    else:
        export_issues.append('未捕获 batch 目录（日志: %s）' % log_path)

    if v3_request:
        try:
            from tools.pipeline.unity_request import write_receipt_from_batch
            receipt = write_receipt_from_batch(os.path.join(BOT_DIR, current_batch), v3_request)
            echo('  ✅ V3 batch receipt: %s (%s)' % (receipt.get('status'), current_batch))
        except Exception as exc:
            echo('  ❌ V3 receipt 验收失败: ' + str(exc))
            export_issues.append('V3 receipt: ' + str(exc))
            sys.exit(1)

    # 4. Agent Data — 刷新池子 + 签名验证（skip-agent-pipeline 时跳过）
    if not args.skip_agent_pipeline:
        agent_data = os.path.join(TOOLS, 'agent_data.py')
        levels_str = ','.join(str(l) for l in LEVELS)
        if os.path.exists(agent_data):
            echo('  Agent data: refreshing pool...')
            ad_result = subprocess.run([sys.executable, '-X', 'utf8', agent_data,
                         '--levels', levels_str, '--output', 'json'],
                         capture_output=True, text=True, timeout=120)
            if ad_result.returncode == 0:
                try:
                    ad = json.loads(ad_result.stdout)
                    echo('  Agent data: %s rel, %s ref, %s levels' %
                         (ad.get('pool',{}).get('reliable','?'),
                          ad.get('pool',{}).get('reference','?'),
                          ad.get('levels_processed','?')))
                except:
                    echo('  Agent data: done (parse skipped)')
        else:
            echo('  Agent data: FAIL — falling back to dump_level_pools')
            dump_script = os.path.join(TOOLS, 'dump_level_pools.py')
            if os.path.exists(dump_script):
                subprocess.run([sys.executable, '-X', 'utf8', dump_script],
                              capture_output=True, text=True, timeout=120)
                echo('  Pool refreshed (fallback)')
    else:
        dump_script = os.path.join(TOOLS, 'dump_level_pools.py')
        result = subprocess.run([sys.executable, '-X', 'utf8', dump_script],
                                capture_output=True, text=True)
        if result.returncode == 0:
            echo('  Pool refreshed')
        else:
            echo('  !! Pool refresh failed: ' +
                 (result.stderr.strip()[-200:] if result.stderr else '?'))

    # 5. 自动运行 post_batch_review
    # 2026-08-14 修：post_batch_review 是批跑后附加分析——它超时/失败不应判定批跑失败
    # （此前 11关大批次 find_best_monotonic O(k^5) 超 60s → TimeoutExpired 冒泡 →
    #   整批被误判失败重跑 4 小时）。现在 try/except 包裹：失败仅警告不中断。
    review_script = os.path.join(TOOLS, 'post_batch_review.py')
    if os.path.exists(review_script) and current_batch:
        echo('  Running post_batch_review...')
        try:
            review_result = subprocess.run(
                [sys.executable, '-X', 'utf8', review_script, '--batch', current_batch,
                 '--full'], capture_output=True, text=True, timeout=300)
            if review_result.returncode == 0:
                echo('  post_batch_review done')
            else:
                echo('  !! post_batch_review failed (exit=' + str(review_result.returncode) +
                     '): ' + (review_result.stderr.strip()[-300:] or review_result.stdout.strip()[-300:]))
        except subprocess.TimeoutExpired:
            echo('  !! post_batch_review timed out (>300s) — 批跑数据已落盘，跳过分析')
        except Exception as _review_ex:
            echo('  !! post_batch_review error: ' + str(_review_ex)[-200:])

    # 6. Agent 流水线：analyze → review（2026-08-05 修复：--skip-agent-pipeline 时跳过，
        #    否则 auto_loop 传 --skip-agent-pipeline 仍会跑 agent_analyze 超时 120s 整批 FAIL）
        agent_analyze = os.path.join(TOOLS, 'agent_analyze.py')
        agent_review = os.path.join(TOOLS, 'agent_review.py')
        if not args.skip_agent_pipeline and os.path.exists(agent_analyze):
            levels_str = ','.join(str(l) for l in LEVELS)
            echo('  Agent analyze...')
            ar = subprocess.run([sys.executable, '-X', 'utf8', agent_analyze,
                 '--levels', levels_str, '--filter-verified', '--output', 'json'],
                 capture_output=True, text=True, timeout=120)
            if ar.returncode == 0:
                echo('  Agent analyze: done')
                if os.path.exists(agent_review):
                    try:
                        analyze_data = json.loads(ar.stdout)
                        # Build combo plan for review
                        combo = {'levels': {}}
                        for r in analyze_data.get('results', []):
                            c = r.get('combo')
                            if c:
                                combo['levels'][str(r['level'])] = {
                                    'difficulty': r.get('difficulty','normal'),
                                    'tiers': [{'wr':t['wr'],'sd':t['sd'],'sc':t['sc'],
                                              'ratios':t['ratios'],'of':t['of']}
                                             for t in c['tiers']]
                                }
                        if combo['levels']:
                            import tempfile
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
                                json.dump(combo, tf)
                                combo_path = tf.name
                            rr = subprocess.run([sys.executable, '-X', 'utf8', agent_review,
                                 '--combo-file', combo_path, '--output', 'json'],
                                 capture_output=True, text=True, timeout=60)
                            os.unlink(combo_path)
                            if rr.returncode == 0:
                                try:
                                    review_data = json.loads(rr.stdout)
                                    p = sum(1 for r in review_data.get('results',[]) if r.get('passed'))
                                    t = len(review_data.get('results',[]))
                                    echo('  Agent review: %d/%d passed' % (p, t))
                                except:
                                    echo('  Agent review: parse error')
                    except:
                        echo('  Agent review: skipped')
            else:
                echo('  Agent analyze: FAIL')
        else:
            echo('  Agent pipeline skipped (--skip-agent-pipeline)')
    # 5.5 展示 post_batch_review 结果（如果可用）
    try:
        review_result
    except NameError:
        pass
    else:
        if review_result.returncode == 0:
            for line in review_result.stdout.split('\n'):
                if any(k in line for k in ['差异', '变化', '汇总', '推荐', '⚠',
                                           '✅', '❌', 'diff']):
                    echo('    ' + line.strip())
            echo('  post_batch_review done')
        else:
            echo('  !! post_batch_review partial: ' +
                 (review_result.stdout.strip()[-200:] or 'check output'))

    # 6. 输出本次结果摘要
    if current_batch:
        dp = os.path.join(BOT_DIR, current_batch)
        if os.path.isdir(dp):
            for td in sorted(os.listdir(dp)):
                tdir = os.path.join(dp, td)
                if not os.path.isdir(tdir):
                    continue
                m = re.search(r'T(\d+)', td)
                if not m:
                    continue
                for sf in glob.glob(os.path.join(tdir, 'campaign-summary-*.csv')):
                    with open(sf, encoding='utf-8-sig') as fh:
                        for row in csv.DictReader(fh):
                            lv = row.get('level', '')
                            wr = row.get('winkate', '')
                            if lv in [str(x) for x in LEVELS] and wr:
                                echo('  L{} T{}: {:.1f}%'.format(
                                    lv, m.group(1), float(wr) * 100))

    echo('=== DONE ===')

    # 7. 2026-08-10 P1b：结构化失败摘要（带恢复路径）——Agent 不用猜失败原因
    # 2026-08-14：新增 export_missing —— Unity 退出码正常但 CSV 没导出（ROUND1 事故）
    if not completed or export_issues:
        RECOVERY = {
            'unity_conflict': '另一个 Unity 实例占用项目——等它关闭或手动关闭后重试',
            'unity_fatal_error': 'Unity 致命错误——查看上方 [Unity] 输出定位具体原因',
            'unity_timeout': 'Unity 超时被杀——检查关卡数量/局数是否过大',
            'export_missing': 'Unity 退出但 CSV 未导出——查 batch-logs/ 下本次日志，定位 ExportCampaignResultToExcel 异常',
        }
        reason = fatal_reason or ('export_missing' if export_issues else 'unknown')
        rec = RECOVERY.get(reason, '查看上方 [Unity] 输出定位原因')
        detail = '; '.join(export_issues[:3]) + ('…' if len(export_issues) > 3 else '')
        echo('RESULT: {"status": "failed", "reason": "%s", "recovery": "%s", "detail": "%s", "log": "%s"}' %
             (reason, rec, detail.replace('"', "'"), log_path))
        sys.exit(1)
