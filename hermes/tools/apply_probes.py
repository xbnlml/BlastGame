#!/usr/bin/env python3
"""从 probe_configs.json 读取探针配置写入 asset。

用法:
  python tools/apply_probes.py 172              # 单关
  python tools/apply_probes.py 172,175,180      # 多关
  python tools/apply_probes.py 170-185          # 范围
  python tools/apply_probes.py 172 --dry-run    # 只验证不写入

与 submit_batch_unity.py 完全解耦——设置配置和跑 bot 是两个独立操作。
"""

import json, os, sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
HERMES = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, HERMES)

from tools.asset_patcher import write_ddc, read_ddc, verify_all

PROBE_CONFIG_PATH = os.path.join(TOOLS_DIR, 'probe_configs.json')


def warden_check(lv, tiers):
    """Warden 闸门：探针写入前强制检查。不通过 → 拒绝写入。
    2026-08-06: W01(sd跨度/单调)/W03(ratios多样性) 已移除——sd/ratios 是探索手段，
    由设计按缺口需要决定，不该硬性约束（用户裁定）。只保留 W02 槽位完整 + W09 探针质量。
    2026-08-06 晚：新增 W09 探针质量检查——今天坏探针（ratios 全 '10,1,1,1,1'、
    空 ratios）从只查 5 槽的闸门溜过去了，导致 Unity dedup 吃槽。"""
    from tools.warden import check_5_slots, check_probe_quality
    checks = [
        ('W02 5槽全填', check_5_slots(tiers)),
        ('W09 探针质量', check_probe_quality(tiers)),
    ]
    fails = []
    for name, (ok, msg) in checks:
        if not ok:
            fails.append(f'{name}: {msg}')
    return fails


def auto_design(lv):
    """探针缺失时自动调用 design_probes 生成，不手工填。"""
    from tools.design_probes import design
    result = design(str(lv))
    if isinstance(result, dict) and any(k.startswith('T') for k in result):
        return result
    return None


def parse_levels(spec):
    levels = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-')
            levels.update(range(int(a), int(b) + 1))
        else:
            levels.add(int(part))
    return sorted(levels)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='应用探针配置到 asset')
    parser.add_argument('levels', help='关卡范围（如 172 或 170-185）')
    parser.add_argument('--dry-run', action='store_true', help='只验证不写入')
    args = parser.parse_args()

    levels = parse_levels(args.levels)

    if not os.path.exists(PROBE_CONFIG_PATH):
        print(f'❌ probe_configs.json 不存在: {PROBE_CONFIG_PATH}')
        sys.exit(1)

    with open(PROBE_CONFIG_PATH) as f:
        probe_configs = json.load(f)

    ok_all = True
    failed_levels = []  # 2026-08-18：记录失败关，供 auto_loop 只跳过失败关
    for lv in levels:
        cfg = probe_configs.get(str(lv))
        if not cfg:
            # 探针缺失 → 自动调用 design_probes 生成，不允许手工拍脑袋
            print(f'  L{lv}: probe_configs.json 无配置，自动调用 design_probes 生成...')
            cfg = auto_design(lv)
            if cfg:
                probe_configs[str(lv)] = cfg
                with open(PROBE_CONFIG_PATH, 'w') as f:
                    json.dump(probe_configs, f, indent=2, ensure_ascii=False)
                print(f'  L{lv}: ✅ 已生成并写入 probe_configs.json')
            else:
                print(f'  L{lv}: ❌ design_probes 无法生成（数据不足），跳过')
                ok_all = False
                failed_levels.append(str(lv))
                continue

        tiers = []
        missing = False
        for i in range(1, 6):
            key = 'T%d' % i
            if key in cfg:
                tiers.append(cfg[key])
            else:
                print(f'  L{lv}: 缺少 {key}')
                missing = True
                break

        if missing or len(tiers) != 5:
            ok_all = False
            failed_levels.append(str(lv))
            continue

        # ── Warden 闸门：写入前强制检查 ──
        warden_fails = warden_check(lv, tiers)
        if warden_fails:
            print(f'  L{lv}: ⛔ Warden BLOCKED — 探针不合规，拒绝写入:')
            for f in warden_fails:
                print(f'    - {f}')
            ok_all = False
            failed_levels.append(str(lv))
            continue
        print(f'  L{lv}: ✅ Warden 通过 (5槽完整)')

        if args.dry_run:
            # 只比对 json 和 asset
            try:
                current = read_ddc(lv)
                match = True
                for i in range(5):
                    exp = tiers[i]
                    got = current[i] if i < len(current) else {}
                    for f in ('sd', 'sc', 'ratios', 'of'):
                        if str(exp.get(f)) != str(got.get(f)):
                            match = False
                            break
                if match:
                    print(f'  L{lv}: ✅ json == asset')
                else:
                    print(f'  L{lv}: ❌ json ≠ asset，需应用')
                    ok_all = False
            except Exception as e:
                print(f'  L{lv}: ❌ 读取错误: {e}')
                ok_all = False
        else:
            ok, msg = write_ddc(lv, tiers)
            if ok:
                # 写后验证
                current = read_ddc(lv)
                match = True
                for i in range(5):
                    exp = tiers[i]
                    got = current[i]
                    for f in ('sd', 'sc', 'ratios', 'of'):
                        if str(exp.get(f)) != str(got.get(f)):
                            match = False
                            print(f'  L{lv} T{i+1}: {f} 预期{exp.get(f)} ≠ asset{got.get(f)}')
                if match:
                    print(f'  L{lv}: ✅ 写入成功')
                else:
                    print(f'  L{lv}: ❌ 写入后校验不通过')
                    ok_all = False
            else:
                print(f'  L{lv}: ❌ {msg}')
                ok_all = False

    if args.dry_run:
        print()
        print('✅ 全部一致' if ok_all else '❌ 有差异，用不带 --dry-run 执行写入')
    else:
        print()
        print('✅ 全部完成' if ok_all else '❌ 部分失败')
    # 2026-08-18：失败关列表输出到 stdout（auto_loop 解析 FAILED_LEVELS 行）
    if failed_levels:
        print(f'FAILED_LEVELS: {",".join(failed_levels)}')

    # 2026-08-18：部分失败时退出码仍为 0（FAILED_LEVELS 已记录失败关，调用方据此处理）——
    # 否则 run_cmd 见非零退出码返回 None，auto_loop 拿不到 FAILED_LEVELS 判成"完全失败"。
    sys.exit(0 if (ok_all or failed_levels) else 1)
