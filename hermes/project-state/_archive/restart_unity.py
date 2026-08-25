#!/usr/bin/env python3
"""历史归档：旧 Unity 重启工具，不再使用。

用法:
  python tools/restart_unity.py --start  # 启动 Unity（未运行才启动）
  当前流程禁止自动结束 Unity 进程；请使用现行 preflight/批跑入口。

注意: 优先使用 submit_batch.py 触发编译，不需要重启 Unity。
      重启会导致 Unity 关闭，请先保存工作。
      检查状态请用 check_unity.py
"""
import os, subprocess, time, glob, sys
from pathlib import Path

PROJECT_PATH = os.environ.get('BLASTGAME_REPO', str(Path.home() / 'Documents' / 'BlastGame'))

def get_project_unity_version():
    try:
        pv = os.path.join(PROJECT_PATH, 'ProjectSettings', 'ProjectVersion.txt')
        for line in open(pv):
            if line.startswith('m_EditorVersion:'):
                return line.split(':', 1)[1].strip()
    except:
        pass
    return None

def find_unity():
    version = get_project_unity_version()
    bases = ['C:\\Program Files\\Unity\\Hub\\Editor']
    for base in bases:
        if version:
            pattern = os.path.join(base, version, 'Editor', 'Unity.exe')
            if os.path.exists(pattern):
                return pattern
        for p in sorted(glob.glob(os.path.join(base, '*', 'Editor', 'Unity.exe')), reverse=True):
            return p
    return None

def check_running():
    r = subprocess.run('tasklist /NH 2>nul | findstr /i "Unity.exe"',
                       shell=True, capture_output=True, text=True)
    return r.returncode == 0

def start_unity():
    u = find_unity()
    if not u:
        print('Unity not found')
        return False
    ver = get_project_unity_version()
    print(f'Starting Unity {ver if ver else "?"}')
    subprocess.Popen([u, '-projectPath', PROJECT_PATH])
    return True

def main():
    force = '--force' in sys.argv
    do_start = '--start' in sys.argv
    if not force and not do_start:
        print(__doc__)
        return
    if force:
        print('Force killing Unity...')
        subprocess.run('taskkill /f /im Unity.exe', shell=True)
        time.sleep(5)
    if not check_running():
        start_unity()
        for _ in range(60):
            time.sleep(2)
            if check_running():
                print('Unity started')
                return
        print('Unity start timeout')
    else:
        print('Unity already running')

if __name__ == '__main__':
    main()
