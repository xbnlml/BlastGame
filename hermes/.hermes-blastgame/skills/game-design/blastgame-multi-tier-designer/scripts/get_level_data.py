"""get_level_data.py — 跨所有数据源检索指定关卡数据

调用: python get_level_data.py <level> [repo_path]
输出: 去重后的配置列表，含来源标注

目录匹配规则（3种模式，见 references/bot-batch-directory-structures.md）：
  1. 单关: 63-63-{ts}
  2. 多关逗号: 52-53_56-{ts}（逗号→下划线）
  3. 范围: L51-100-T{n}-{ts}-batch-range（含该关）

数据源优先级: Bot → +Summary → +Phase2 → +Phase1 → +自推
"""
import csv, glob, re, os, sys

def dir_has_level(name, lv):
    """检查目录名是否包含指定关卡（3种命名模式）"""
    if name.startswith(f'{lv}-{lv}-'):
        return True
    m = re.match(r'^(\d[\d_]+)-\d{4}T', name)
    if m:
        parts = m.group(1).split('_')
        for p in parts:
            if p == str(lv): return True
            if '-' in p:
                a,b = p.split('-')
                if a.isdigit() and b.isdigit() and int(a) <= lv <= int(b): return True
    m = re.match(r'^L(\d+)-(\d+)', name)
    if m and int(m.group(1)) <= lv <= int(m.group(2)):
        return True
    return False

def get_level_data(level: int, repo: str = "."):
    """
    返回 [(wr, sd, sc, ratios, of, source_label, is_current)]
    - Type B（范围格式）：config 为 '?'（无配置参数），但仍返回
    - Type A（嵌套格式）：有 campaign-attempts 可读配置
    """
    results = []
    bot_base = os.path.join(repo, 'telemetry', 'bot')
    if not os.path.isdir(bot_base):
        return results

    for entry in sorted(os.listdir(bot_base)):
        full = os.path.join(bot_base, entry)
        if not os.path.isdir(full) or not dir_has_level(entry, level):
            continue

        # Type B (flat) — 维度范围/单关扁平结构
        for sf in glob.glob(os.path.join(full, 'campaign-summary-*.csv')):
            with open(sf, encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('level') == str(level):
                        tm = re.search(r'T(\d+)', sf)
                        t = tm.group(1) if tm else '?'
                        results.append((
                            float(row['winkate']),
                            '?', '?', '?', '?',
                            f'{entry} T{t}',
                            'current' if '2026-07-03T15-45' in entry else 'old'
                        ))

        # Type A (nested) — 标准子目录结构
        for sub in sorted(os.listdir(full)):
            sub_dir = os.path.join(full, sub)
            if not os.path.isdir(sub_dir):
                continue
            tm = re.search(r'T(\d+)', sub)
            t = tm.group(1) if tm else '?'
            for sf in glob.glob(os.path.join(sub_dir, 'campaign-summary-*.csv')):
                with open(sf, encoding='utf-8-sig') as f:
                    for row in csv.DictReader(f):
                        if row.get('level') == str(level):
                            wr = float(row['winkate'])
                            sd = sc = rat = of = '?'
                            for af in glob.glob(os.path.join(sub_dir, 'campaign-attempts-*.csv')):
                                with open(af, encoding='utf-8-sig') as f2:
                                    r = next(csv.DictReader(f2), None)
                                    if r:
                                        sd, sc, rat, of = (
                                            r['startDifficulty'], r['shuffleSplitCount'],
                                            r['shuffleSplitRatios'], r['shuffleOverflowFactor']
                                        )
                            results.append((
                                wr, sd, sc, rat, of,
                                f'{entry} T{t}',
                                'current' if '2026-07-03T15-45' in entry else 'old'
                            ))
    return results

if __name__ == '__main__':
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 63
    repo = sys.argv[2] if len(sys.argv) > 2 else 'C:/Users/Administrator/Documents/BlastGame'
    data = get_level_data(lv, repo)
    # dedup by config
    seen = {}
    for wr,sd,sc,rat,of,src,cur in sorted(data, key=lambda x: (0 if x[6]=='current' else 1, -x[0])):
        key = (sd,sc,rat,of) if ('?','?','?','?') != (sd,sc,rat,of) else src
        if key not in seen:
            seen[key] = (wr, src, cur)
    print(f'L{lv}:\n')
    for key, (wr,src,cur) in sorted(seen.items(), key=lambda x: -x[1][0]):
        m = ' ← current' if cur == 'current' else ''
        sd,sc,rat,of = key if isinstance(key, tuple) else ('?','?','?','?')
        print(f'  {wr*100:5.1f}%  sd={sd} sc={sc} r={rat} of={of}  [{src}]{m}')
    print(f'\n共 {len(seen)} 个配置')
