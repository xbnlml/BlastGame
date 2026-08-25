#!/usr/bin/env python3
"""检查 Unity 运行状态

只检查, 不修改。不杀进程, 不启动 Unity。

用法:
  python tools/check_unity.py
"""
import os, subprocess
from pathlib import Path

PROJECT_PATH = os.environ.get('BLASTGAME_REPO', str(Path.home() / 'Documents' / 'BlastGame'))

def get_version():
    try:
        pv = os.path.join(PROJECT_PATH, 'ProjectSettings', 'ProjectVersion.txt')
        for line in open(pv):
            if line.startswith('m_EditorVersion:'):
                return line.split(':', 1)[1].strip()
    except:
        pass
    return None

def check_running():
    r = subprocess.run('tasklist /NH 2>nul | findstr /i "Unity.exe"',
                       shell=True, capture_output=True, text=True)
    return r.returncode == 0

def main():
    if check_running():
        ver = get_version()
        print(f'Running ({ver if ver else "?"})')
    else:
        print('Stopped')

if __name__ == '__main__':
    main()
