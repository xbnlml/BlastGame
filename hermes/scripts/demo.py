#!/usr/bin/env python3
"""BlastGame 一键演示（只读，约 60 秒）。

用法: python scripts/demo.py

按数据闭环顺序执行只读命令，展示系统在真实数据上的工作：
  目标真源 → 最优组合选档 → 判定语义 → 全局状态 → 一致性验证
"""
import os
import subprocess
import sys
import time

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERMES)

DEMO_LEVELS = '86,108,119,122'


def run(title, cmd):
    print(f'\n{"=" * 70}\n▶ {title}\n$ {cmd}\n{"=" * 70}')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, env=env, timeout=180)
    out = (proc.stdout or '').strip()
    err = (proc.stderr or '').strip()
    if proc.returncode != 0:
        print(f'❌ 退出码 {proc.returncode}')
        if err:
            print(err[-500:])
        return False
    print(out[-2500:])
    return True


def main():
    start = time.time()
    ok = True
    print('BlastGame 数据闭环 Demo（全部只读，使用仓库内真实实测数据）\n')

    ok &= run('① 目标真源（Excel 唯一权威）',
              f'python tools/read_target_wr.py {DEMO_LEVELS}')
    ok &= run('② 最优五档组合选档（档差可接受带 + DB 全绿优先 + 稳定性护栏）',
              f'python tools/find_best_combo.py {DEMO_LEVELS}')
    ok &= run('③ 判定引擎（gap 语义 / 目标偏差 / 合格-接近-不合格）',
              f'python tools/judge_level.py 86,108,119')
    ok &= run('④ 全局状态快照（board 状态 + 每关最优五档）',
              f'python tools/state_snapshot.py --levels 51,86,108,119,143')
    ok &= run('⑤ 落库一致性（asset ↔ DB ↔ 池子三方对账）',
              f'python tools/compare_level_db.py --levels 86,108')

    print(f'\n{"=" * 70}')
    print(f'Demo 完成：{time.time() - start:.0f} 秒，{"全部通过 ✅" if ok else "有失败项 ❌（见上）"}')
    print('详细说明见 docs/demo-guide.md')
    print('=' * 70)


if __name__ == '__main__':
    main()