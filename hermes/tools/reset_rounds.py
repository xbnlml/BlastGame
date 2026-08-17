"""改关卡后重置全自动调优轮数（2026-08-06 流程补全）

背景：用户改关卡后，auto_loop 会沿用旧轮数（如已 7 轮），下一轮直接判
"改关卡"——新关卡设计没有重新获得 MAX_ROUNDS 轮机会。改关卡必须重置轮数。

用法：
  python3 tools/reset_rounds.py 154 198        # 重置指定关
  python3 tools/reset_rounds.py --all          # 重置全部
  python3 tools/reset_rounds.py --list         # 只列出当前轮数

改关卡流程（用户确认后）：
  1. 用户改关卡配置（Unity 侧）
  2. 主 agent 手动 retire_level 设时间防线（如适用）
  3. **python3 tools/reset_rounds.py <lv>**  ← 本工具
  4. board.md 状态更新
"""
import argparse, json, os, sys

ROUNDS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'project-state', '_rounds.json')


def load():
    if os.path.isfile(ROUNDS):
        with open(ROUNDS) as f:
            return json.load(f)
    return {}


def save(d):
    os.makedirs(os.path.dirname(ROUNDS), exist_ok=True)
    with open(ROUNDS, 'w') as f:
        json.dump(d, f, indent=2)


def main():
    ap = argparse.ArgumentParser(description='改关卡后重置全自动调优轮数')
    ap.add_argument('levels', nargs='*', type=int, help='关卡号（可多个）')
    ap.add_argument('--all', action='store_true', help='重置全部')
    ap.add_argument('--list', action='store_true', help='只列出当前轮数')
    args = ap.parse_args()

    d = load()
    if args.list:
        print('当前轮数:')
        for lv, r in sorted(d.items()):
            print(f'  L{lv}: {r} 轮')
        print(f'  共 {len(d)} 关有记录')
        return

    if args.all:
        reset = list(d.keys())
        save({})
        print(f'已重置 {len(reset)} 关: {sorted(reset)}')
        return

    if not args.levels:
        ap.print_help()
        return

    reset = []
    for lv in args.levels:
        key = str(lv)
        if key in d:
            old = d.pop(key)
            reset.append((lv, old))
    save(d)
    for lv, old in reset:
        print(f'L{lv}: 轮数已重置（原 {old} 轮 → 0）')
    for lv in args.levels:
        if str(lv) not in [r[0] for r in reset] and str(lv) in d:
            pass
    not_found = [lv for lv in args.levels if (lv, None) not in [(r[0], None) for r in reset]
                 and str(lv) not in [str(r[0]) for r in reset]]
    if not_found:
        print(f'未在记录中的关（本就 0 轮，无需重置）: {not_found}')


if __name__ == '__main__':
    main()
