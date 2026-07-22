import os, re, json, shutil

REPO = os.environ.get('BLASTGAME_REPO', r'C:\Users\Administrator\Documents\BlastGame')
ASSET_DIR = os.path.join(REPO, 'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test')
BACKUP_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets_backup')
BACKUP_DIR = os.path.normpath(BACKUP_DIR)
os.makedirs(BACKUP_DIR, exist_ok=True)


def _asset_path(lv):
    return os.path.join(REPO, 'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test', f'{lv}.asset')


def _backup(lv):
    bak = os.path.join(BACKUP_DIR, f'{lv}.asset.bak')
    src = _asset_path(lv)
    if os.path.isfile(src):
        shutil.copy2(src, bak)
    return bak


def _restore(bak, lv):
    if os.path.isfile(bak):
        shutil.copy2(bak, _asset_path(lv))


def verify_integrity(lv):
    fp = _asset_path(lv)
    if not os.path.isfile(fp):
        return False, f'missing {fp}'
    sz = os.path.getsize(fp)
    if sz < 1000:
        return False, f'too small ({sz}B)'
    with open(fp, 'r', encoding='utf-8') as f:
        raw = f.read()
    if 'DynamicDifficultyConfigs' not in raw:
        return False, 'missing DynamicDifficultyConfigs'
    if 'customCellDrawingListV2' not in raw:
        return False, 'missing customCellDrawingListV2'
    return True, f'OK ({sz}B)'


def verify_all(levels):
    fails = []
    for lv in levels:
        ok, msg = verify_integrity(lv)
        if not ok:
            fails.append((lv, msg))
    return fails


def find_ddc_block(lines):
    start = end = None
    for i, line in enumerate(lines):
        if 'DynamicDifficultyConfigs:' in line:
            start = i
        if 'customCellDrawingListV2:' in line and start is not None:
            end = i
            break
    if 'customCellDrawingListV2:' not in ''.join(lines) and start is not None:
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.strip() and not line.startswith(' ') and not line.startswith('-'):
                end = i
                break
    return start, end


def read_ddc(lv):
    fp = _asset_path(lv)
    if not os.path.isfile(fp):
        return f'missing {fp}'
    with open(fp, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    start, end = find_ddc_block(lines)
    if start is None:
        return '找不到 DynamicDifficultyConfigs'
    if end is None:
        return '找不到结束标记'
    configs = []
    i = start + 1
    while i < end:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # 处理 "- StartDifficulty: 1" 这种同行 key-value
        if line.startswith('- '):
            cfg = {}
            content = line[2:].strip()  # "StartDifficulty: 1"
            if ':' in content:
                k, v = content.split(':', 1)
                k = k.strip()
                v = v.strip().strip('"')
                if k == 'StartDifficulty':
                    try:
                        cfg['sd'] = int(v)
                    except ValueError:
                        cfg['sd'] = v
            i += 1
            # 读取后续缩进行
            while i < end:
                sub = lines[i].strip()
                if sub.startswith('- ') or not sub:
                    break
                if ':' in sub:
                    k, v = sub.split(':', 1)
                    k = k.strip()
                    v = v.strip().strip('"')
                    if k == 'StartDifficulty':
                        try:
                            cfg['sd'] = int(v)
                        except ValueError:
                            cfg['sd'] = v
                    elif k == 'ShuffleSplitCount':
                        try:
                            cfg['sc'] = int(v)
                        except ValueError:
                            cfg['sc'] = v
                    elif k == 'ShuffleSplitRatios':
                        cfg['ratios'] = v
                    elif k == 'ShuffleOverflowFactor':
                        try:
                            cfg['of'] = float(v)
                        except ValueError:
                            cfg['of'] = v
                i += 1
            if cfg:
                configs.append(cfg)
        else:
            i += 1
    return configs


def write_ddc(lv, tiers):
    if len(tiers) != 5:
        return False, f'需要5档配置，收到{len(tiers)}'
    fp = _asset_path(lv)
    ok, msg = verify_integrity(lv)
    if not ok:
        return False, f'写入前: {msg}'
    bak = _backup(lv)
    orig_sz = os.path.getsize(fp)
    with open(fp, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    start, end = find_ddc_block(lines)
    if start is None:
        return False, '找不到 DynamicDifficultyConfigs'
    if end is None:
        return False, '找不到 customCellDrawingListV2'
    new_block = [lines[start]]
    for t in tiers:
        new_block.append(f'    - StartDifficulty: {t["sd"]}\n')
        new_block.append(f'      ShuffleSplitCount: {t["sc"]}\n')
        new_block.append(f'      ShuffleSplitRatios: {t["ratios"]}\n')
        new_block.append(f'      ShuffleOverflowFactor: {t["of"]}\n')
    new_lines = lines[:start] + new_block + lines[end:]
    with open(fp, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    indent_cc = '    ' if '    DynamicDifficultyConfigs' in lines[start] else '  '
    with open(fp, 'r', encoding='utf-8') as f:
        raw = f.read()
    raw2 = re.sub(r'(?<=\n)customCellDrawingListV2:', indent_cc + r'customCellDrawingListV2:', raw)
    if raw2 != raw:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(raw2)
    ok2, msg2 = verify_integrity(lv)
    if not ok2:
        _restore(bak, lv)
        return False, f'写后回滚: {msg2}'
    new_sz = os.path.getsize(fp)
    if abs(new_sz - orig_sz) > orig_sz * 0.15:
        _restore(bak, lv)
        return False, f'大小变化({orig_sz}→{new_sz})已回滚'
    return True, f'OK ({new_sz}B)'
