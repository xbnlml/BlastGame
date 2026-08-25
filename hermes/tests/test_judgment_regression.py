#!/usr/bin/env python3
"""判定规则回归集：历史用户裁决固化为测试——改 rules.json/judge_level 必跑。

2026-08-17 建立（标准保障机制 P0）：
- 判定语义多次被用户纠正（接近≠入库、5/10 分级、dev=10 贴线算接近）
- 每次都是"用户发现→修"，没有防回归——改规则可能悄悄改坏历史裁决
- 本套件把历史裁决固化为 fixture，断言 check_judgment 输出不变

用法：python tests/test_judgment_regression.py
退出码 0=全部通过；非 0=判定语义被改坏。
"""
import sys
import os

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERMES)

FAILURES = []


def check(name, actual, expect, detail=''):
    status = '✅' if actual == expect else '❌'
    if actual != expect:
        FAILURES.append(f'{name}: 期望 {expect} 实际 {actual} {detail}')
    print(f'  {status} {name}')


def main():
    from tools.judge_level import check_judgment

    print('=== 目标偏差 5/10 分级（2026-08-17 用户定稿）===')
    # 1. 全达标 → 合格
    r = check_judgment({'T1': 80, 'T2': 80, 'T3': 60, 'T4': 45, 'T5': 45}, 'normal', [80, 80, 60, 45, 45])
    check('全达标=合格', r[0], '合格')

    # 2. dev=10 贴线 → DB非绿，不合格（用户明确：达到10pp也不能绿色）
    r = check_judgment({'T1': 77, 'T2': 77, 'T3': 59, 'T4': 35, 'T5': 35}, 'normal', [80, 80, 60, 45, 45])
    check('dev=10贴线=不合格', r[0], '不合格', f'reasons={r[1]}')

    # 3. dev=7 在 5-10 之间 → 接近（L186 T1 案例）
    r = check_judgment({'T1': 63, 'T2': 50, 'T3': 39.2, 'T4': 28.5, 'T5': 18.5}, 'hard', [70, 55, 40, 30, 20])
    check('dev=7=接近', r[0], '接近')

    # 4. dev=13 > 12（10+容差2）→ 不合格（硬违规）
    r = check_judgment({'T1': 93, 'T2': 93, 'T3': 60, 'T4': 45, 'T5': 45}, 'normal', [80, 80, 60, 45, 45])
    check('dev=13=不合格', r[0], '不合格')

    # 4b. dev=12 虽在目标偏差容差内，但 DB 已非绿 → 不合格（2026-08-20 新标准）
    r = check_judgment({'T1': 92, 'T2': 92, 'T3': 60, 'T4': 45, 'T5': 45}, 'normal', [80, 80, 60, 45, 45])
    check('dev=12非绿=不合格', r[0], '不合格', f'reasons={r[1]}')

    # 4c. dev=10.1 已超过 DB 绿色线，即使未超过 target 容差也不能接近
    r = check_judgment({'T1': 90.1, 'T2': 90.1, 'T3': 60, 'T4': 45, 'T5': 45}, 'normal', [80, 80, 60, 45, 45])
    check('dev=10.1非绿=不合格', r[0], '不合格', f'reasons={r[1]}')

    # 5. dev=5 正好 = 完全接受线 → 合格（≤5 合格）
    r = check_judgment({'T1': 85, 'T2': 85, 'T3': 60, 'T4': 45, 'T5': 45}, 'normal', [80, 80, 60, 45, 45])
    check('dev=5=合格', r[0], '合格')

    print('=== 接近≠入库语义（2026-08-17）===')
    # action 行为由 tests/pipeline/test_judge_rounds.py 通过临时 rounds 文件验证。

    print('=== 判定对 gap 边界（历史案例）===')
    # 7. L152 案例：gap 差 0.01pp 接近带容差（near_tolerance_pp=1）
    #    T3→T5 gap=9.99 < 10 差 0.01 → 接近不是不合格（带容差）
    r = check_judgment({'T1': 80, 'T2': 80, 'T3': 60, 'T4': 50.01, 'T5': 50.01}, 'normal')
    check('gap=9.99进入接近带', r[0], '接近', f'reasons={r[1]}')

    print()
    if FAILURES:
        print(f'❌ {len(FAILURES)} 项失败:')
        for f in FAILURES:
            print(f'  - {f}')
        sys.exit(1)
    print('✅ 判定回归全部通过：历史裁决语义未变')
    sys.exit(0)


if __name__ == '__main__':
    main()
