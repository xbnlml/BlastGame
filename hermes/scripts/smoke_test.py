"""smoke_test.py — 核心工具链一键冒烟验证（2026-08-10 新增）

改动工具后跑一遍，防回归。覆盖核心链路：
  1. 工具编译（py_compile）
  2. verify_asset_db_match（asset↔DB 一致性，只读）
  3. compare_level_db（只读 DB/池对比）
  4. pipeline_stats（批次统计，只读）
  5. Warden CLI 契约（真实提交闸门由 preflight 调用）
  6. design_probes 只读设计（不写 asset）
  7. auto_loop CLI 契约

用法: python scripts/smoke_test.py
退出码: 0 = 全过；1 = 有失败
"""
import sys, os, subprocess

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(HERMES, 'tools')
SCRIPTS = os.path.join(HERMES, 'scripts')
sys.path.insert(0, HERMES)

# 用当前 asset↔DB 一致的关做冒烟样本
SAMPLE = '86,108,119,122'

TOOL_FILES = [
    os.path.join(TOOLS, 'reimport.py'),
    os.path.join(TOOLS, 'judge_level.py'),
    os.path.join(TOOLS, 'compare_level_db.py'),
    os.path.join(TOOLS, 'verify_asset_db_match.py'),
    os.path.join(TOOLS, 'pipeline_stats.py'),
    os.path.join(TOOLS, 'warden.py'),
    os.path.join(TOOLS, 'design_probes.py'),
    os.path.join(TOOLS, 'find_best_combo.py'),
    os.path.join(TOOLS, 'dump_level_pools.py'),
    os.path.join(SCRIPTS, 'auto_loop.py'),
]

def run(cmd, timeout=120):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       timeout=timeout, cwd=HERMES)
    return r

def main():
    passed = 0
    failed = []

    # 1. 编译检查
    for f in TOOL_FILES:
        r = run([sys.executable, '-m', 'py_compile', f])
        if r.returncode == 0:
            passed += 1
        else:
            failed.append(f'编译失败: {os.path.basename(f)}: {r.stderr[-200:]}')
    print(f'1. 编译: {passed}/{len(TOOL_FILES)}')

    # 2. verify_asset_db_match（核心：asset↔DB 一致）
    r = run([sys.executable, os.path.join(TOOLS, 'verify_asset_db_match.py'), '--levels', SAMPLE])
    if r.returncode == 0 and '严格一致' in r.stdout:
        passed += 1
        print('2. verify_asset_db_match: ✅')
    else:
        failed.append(f'verify_asset_db_match: rc={r.returncode} {r.stdout[-200:]}')
        print('2. verify_asset_db_match: ❌')

    # 3. compare_level_db（只读 DB 对比）
    r = run([sys.executable, os.path.join(TOOLS, 'compare_level_db.py'), '--levels', SAMPLE])
    if r.returncode == 0 and '✅ 基本一致' in r.stdout:
        passed += 1
        print('3. compare_level_db: ✅')
    else:
        failed.append(f'compare_level_db: rc={r.returncode} {r.stderr[-200:]}')
        print('3. compare_level_db: ❌')

    # 4. pipeline_stats（批次统计）
    r = run([sys.executable, os.path.join(TOOLS, 'pipeline_stats.py')])
    if r.returncode == 0 and '批次' in r.stdout:
        passed += 1
        print('4. pipeline_stats: ✅')
    else:
        failed.append(f'pipeline_stats: rc={r.returncode} {r.stderr[-200:]}')
        print('4. pipeline_stats: ❌')

    # 5. Warden 的真实提交闸门由 preflight 调用；这里只检查 CLI 契约
    r = run([sys.executable, os.path.join(TOOLS, 'warden.py'), '--help'])
    if r.returncode == 0 and 'Warden' in r.stdout:
        passed += 1
        print('5. warden CLI: ✅')
    else:
        failed.append(f'warden CLI: rc={r.returncode} {r.stdout[-200:]}')
        print('5. warden CLI: ❌')

    # 6. design_probes 可达性预检（L85 应输出 ⚠ 可达性预检）
    r = run([sys.executable, os.path.join(TOOLS, 'design_probes.py'), '85'], timeout=180)
    if r.returncode == 0:
        passed += 1
        print('6. design_probes: ✅')
        if '可达性预检' in r.stdout:
            print('   可达性预检触发: ✅ (L85 天花板提示)')
            passed += 1
        else:
            print('   ⚠ 可达性预检未触发（数据可能已变化）')
    else:
        failed.append(f'design_probes: rc={r.returncode} {r.stderr[-200:]}')
        print('6. design_probes: ❌')

    # 7. auto_loop --help（入口正常 + --probe-games 参数）
    r = run([sys.executable, os.path.join(SCRIPTS, 'auto_loop.py'), '--help'])
    if r.returncode == 0 and '--resume' in r.stdout and '--probe-games' in r.stdout:
        passed += 1
        print('7. auto_loop --help + --resume + --probe-games: ✅')
    else:
        failed.append(f'auto_loop --help: {r.stdout[-100:]}')
        print('7. auto_loop --help: ❌')

    print(f'\n=== smoke_test: {passed} passed, {len(failed)} failed ===')
    for f in failed:
        print(f'  ❌ {f}')
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
