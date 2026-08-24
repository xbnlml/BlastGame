#!/usr/bin/env python3
"""只读工具冒烟测试：核心工具必须能跑且有输出。

背景（2026-08-24）：state_snapshot.py 曾因 board.md 格式漂移静默失效
（解析出零关卡），99+ 回归没抓住——因为回归只断言具体输出，
没有覆盖"工具本身能跑"。本套件每个核心只读工具跑最小参数，
断言退出码 0 且输出非空，防止工具悄悄坏掉。

用法：python -m unittest tests.pipeline.test_tool_smoke -v
"""
import os
import subprocess
import sys
import unittest

HERMES = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOOLS = [
    # (文件名, 参数) —— 只读、最小参数、用真实关卡 86（已入库关）
    ('tools/read_target_wr.py', ['86']),
    ('tools/find_best_combo.py', ['86']),
    ('tools/judge_level.py', ['86']),
    ('tools/state_snapshot.py', ['--levels', '86']),
    ('tools/verify_pool_data.py', ['--levels', '86']),
    ('tools/audit_imported.py', ['--levels', '86']),
    ('tools/param_knowledge.py', ['--ratios-pool']),
    ('tools/diff_state.py', ['86']),
]


class ToolSmokeTest(unittest.TestCase):
    def test_tools_run_and_output(self):
        failed = []
        for tool, args in TOOLS:
            proc = subprocess.run(
                [sys.executable, os.path.join(HERMES, tool)] + args,
                capture_output=True, text=True, timeout=120,
                cwd=HERMES,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            )
            out = (proc.stdout or '').strip()
            if proc.returncode != 0 or not out:
                failed.append(f'{tool}: rc={proc.returncode} '
                              f'stderr={proc.stderr[-300:]!r}')
        self.assertEqual([], failed, f'工具冒烟失败:\n' + '\n'.join(failed))


if __name__ == '__main__':
    unittest.main(verbosity=2)