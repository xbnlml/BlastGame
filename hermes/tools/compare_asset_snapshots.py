"""对比 telemetry 各批次 level-assets 快照 vs 当前 asset（difflib 精确到行）。
关卡配置一致（0 差异行）的批次，其参数→胜率对应关系才有效。
"""
import os, re, sys, glob, difflib
from datetime import datetime

sys.path.insert(0, r'D:\download\BlastGame\hermes')
from tools.asset_patcher import _asset_path

OPT_DIR = r'C:\Users\Administrator\Documents\BlastGame\telemetry\multi-tier-opt'

def dir_timestamp(name):
    m = re.findall(r'(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})', name)
    if m:
        try:
            return datetime.strptime(m[-1], '%Y-%m-%dT%H-%M-%S')
        except ValueError:
            return None
    return None

def strip_irrelevant(content):
    """剔除 scoreMultipliers 和 DynamicDifficultyConfigs 两段（不是牌面数据）"""
    lines = content.splitlines()
    out = []
    skip_indent = None  # 当前跳过段的字段缩进
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if skip_indent is not None:
            # 遇到缩进更浅/同级 且不是列表项的行 = 新字段，结束跳过
            if indent <= skip_indent and not stripped.startswith('- '):
                skip_indent = None
                continue  # 重新处理这行
            i += 1
            continue
        if stripped in ('scoreMultipliers:', 'DynamicDifficultyConfigs:'):
            skip_indent = indent
            i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out)

def main():
    snapshots = {}
    for batch in sorted(os.listdir(OPT_DIR)):
        bp = os.path.join(OPT_DIR, batch)
        if not os.path.isdir(bp):
            continue
        ts = dir_timestamp(batch)
        if ts is None:
            continue
        for sp in glob.glob(os.path.join(bp, '**', 'level-assets', 'test', '*.asset'), recursive=True):
            lv = os.path.basename(sp).replace('.asset', '')
            snapshots.setdefault(lv, []).append((batch, ts, sp))

    print(f"{'关':>4}  快照  最新快照时间   差异行  ✅一致/❌不同  差异内容(牌面相关)")
    print('-' * 110)
    for lv in sorted(snapshots.keys(), key=int):
        cur_path = _asset_path(int(lv))
        if not cur_path or not os.path.isfile(cur_path):
            print(f'{lv:>4}  当前 asset 不存在')
            continue
        cur_raw = open(cur_path, encoding='utf-8', errors='replace').read()
        snap_raw = None
        snaps = sorted(snapshots[lv], key=lambda x: x[1])
        latest_batch, latest_ts, latest_sp = snaps[-1]
        snap_raw = open(latest_sp, encoding='utf-8', errors='replace').read()

        cur_lines = strip_irrelevant(cur_raw).splitlines()
        snap_lines = strip_irrelevant(snap_raw).splitlines()

        diff = list(difflib.unified_diff(snap_lines, cur_lines, lineterm='', n=0))
        n_diff = len(diff)
        ts_str = latest_ts.strftime('%m-%d %H:%M')
        if n_diff == 0:
            print(f'{lv:>4}  {len(snaps):>3}  {ts_str}      0   ✅ 牌面一致')
        else:
            change_lines = [l for l in diff if l.startswith(('-', '+')) and not l.startswith(('---', '+++'))]
            desc = '; '.join(l.strip() for l in change_lines[:4])
            print(f'{lv:>4}  {len(snaps):>3}  {ts_str}      {n_diff:>2}   ❌  {desc}')

if __name__ == '__main__':
    main()
