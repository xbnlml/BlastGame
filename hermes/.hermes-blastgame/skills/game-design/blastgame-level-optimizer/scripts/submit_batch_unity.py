#!/usr/bin/env python3
"""通过 Unity batch mode 提交并运行 bot 批跑（使用 Jenkins 官方入口）。

用法:
  python scripts/submit_batch_unity.py "56,57,71,86" --games 400
  python scripts/submit_batch_unity.py "70" --games 400 --tiers "4,5"
  python scripts/submit_batch_unity.py "56" --games 400 --tiers 3 --skip-patch

官方入口: BlastGame.Editor.BlastBotJenkinsBatchEntry.RunFromCommandLine
日志: -logFile - 输出到 stdout，实时可见
"""
import os, sys, time, subprocess, re

REPO = r'C:\Users\Administrator\Documents\BlastGame'
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools')
BOT_DIR = os.path.join(REPO, 'telemetry', 'bot')
UNITY_EXE = r'C:\Program Files\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe'
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
    args = parser.parse_args()
    LEVELS = parse_levels(args.levels)
    if not args.tiers:
        echo("ERROR: --tiers 必填。探针全五档: --tiers 1,2,3,4,5，验证: --tiers 3")
        sys.exit(1)
    # ... (full implementation follows)
