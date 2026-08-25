import os, re, json, shutil, hashlib

REPO = os.environ.get('BLASTGAME_REPO', os.path.join(os.path.expanduser('~'), 'Documents', 'BlastGame'))
ASSET_DIR = os.path.join(REPO, 'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test')
BACKUP_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets_backup')
BACKUP_DIR = os.path.normpath(BACKUP_DIR)
os.makedirs(BACKUP_DIR, exist_ok=True)


def _asset_path(lv):
    """Find asset file, handling subdirectories for L101-200."""
    base = os.path.join(REPO, 'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test')
    direct = os.path.join(base, f'{lv}.asset')
    if os.path.isfile(direct):
        return direct
    # Search subdirectories
    for root, dirs, files in os.walk(base):
        if f'{lv}.asset' in files:
            return os.path.join(root, f'{lv}.asset')
    return direct


def _backup(lv):
    bak = os.path.join(BACKUP_DIR, f'{lv}.asset.bak')
    src = _asset_path(lv)
    if os.path.isfile(src):
        shutil.copy2(src, bak)
    return bak


def _backup_after_write(lv):
    """write_ddc 写入成功后备份最终版本，防 git pull 覆盖后无法恢复入库配置。

    2026-08-04：.bak 是写入前版本（防写坏回滚）；latest.bak 是写入后版本（防 git 覆盖）。
    """
    latest = os.path.join(BACKUP_DIR, f'{lv}.asset.latest.bak')
    src = _asset_path(lv)
    if os.path.isfile(src):
        shutil.copy2(src, latest)
    return latest


def _restore(bak, lv):
    if os.path.isfile(bak):
        shutil.copy2(bak, _asset_path(lv))


def verify_asset(lv, expected_5tiers):
    """比对 asset 四个字段与预期是否一致。返回 (bool, str msg)。"""
    try:
        actual = read_ddc(lv)
    except Exception as e:
        return False, f'读取失败: {e}'
    if len(actual) != 5:
        return False, f'档位数={len(actual)}，需要5'
    for i in range(5):
        exp = expected_5tiers[i]
        got = actual[i]
        for f in ('sd', 'sc', 'ratios', 'of'):
            ev = exp.get(f, '')
            gv = got.get(f, '')
            if f == 'of':
                if float(ev) != float(gv):
                    return False, f'T{i+1} {f}: 预期{ev} ≠ asset{gv}'
            elif str(ev) != str(gv):
                return False, f'T{i+1} {f}: 预期{ev} ≠ asset{gv}'
    return True, 'OK'


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
    # 完整校验四元组
    cfg = read_ddc(lv)
    if isinstance(cfg, str):
        return False, cfg
    if len(cfg) != 5:
        return False, f'档位数={len(cfg)}≠5'
    for i, t in enumerate(cfg):
        sc = int(t.get('sc', 0))
        ratios = str(t.get('ratios', ''))
        ratios_parts = [x.strip() for x in ratios.split(',') if x.strip()]
        if sc != len(ratios_parts):
            return False, f'T{i+1}: sc={sc}≠len(ratios)={len(ratios_parts)}'
        of_v = float(t.get('of', 0))
        if of_v < 0 or of_v > 1.01:
            return False, f'T{i+1}: of={of_v} 超出[0,1]'
        sd = int(t.get('sd', 0))
        if sd < 0 or sd > 200:
            return False, f'T{i+1}: sd={sd} 超出范围'
        for v in ratios_parts:
            try:
                n = int(v)
                if n < 0:
                    return False, f'T{i+1}: ratios含负值({v})'
            except:
                return False, f'T{i+1}: ratios非整数({v})'
    return True, f'OK ({sz}B)'


def verify_all(levels):
    fails = []
    for lv in levels:
        ok, msg = verify_integrity(lv)
        if not ok:
            fails.append((lv, msg))
    return fails


def level_sig(lv_or_path):
    """返回关卡设计签名（不含 DDC 参数和 scoreMultipliers）。

    2026-08-04 升级：同时剔除 scoreMultipliers（星星需求参数）——
    该参数全局调整（如 1.0→0.8x）不影响"参数→胜率"对应关系，
    level_sig 只代表关卡牌面（布局/格子结构等）。
    提取 asset 文件中除 DynamicDifficultyConfigs、scoreMultipliers
    两段之外的全部内容做 SHA256。
    用于判断 bot/opt 快照和当前关卡是否同一设计——不一致说明关卡已被修改，老数据作废。
    """
    if isinstance(lv_or_path, int):
        path = _asset_path(lv_or_path)
    else:
        path = lv_or_path
    if not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 找要剔除的段（DynamicDifficultyConfigs 和 scoreMultipliers）
    remove_ranges = []
    for target in ('DynamicDifficultyConfigs:', 'scoreMultipliers:'):
        start = end = -1
        for i, line in enumerate(lines):
            if target in line and start < 0:
                start = i
                break
        if start < 0:
            continue
        # 段结束 = 下一个缩进小于段首行的字段
        base_indent = len(lines[start]) - len(lines[start].lstrip())
        end = len(lines)
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= base_indent and not line.strip().startswith('- '):
                end = i
                break
        remove_ranges.append((start, end))

    # 保留不在剔除段内的行
    kept = []
    for i, line in enumerate(lines):
        if any(start <= i < end for start, end in remove_ranges):
            continue
        kept.append(line)
    content = ''.join(kept).encode('utf-8')
    return hashlib.sha256(content).hexdigest()


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


def config_sig(tier):
    """返回配置归一化签名，用于比对两个配置是否相同。
    忽略 of 的浮点精度差异（0.5 vs 0.500），ratios 的空格差异。"""
    sd = tier.get('sd', '?')
    sc = tier.get('sc', '?')
    ratios = str(tier.get('ratios', '')).replace(' ', '')
    try:
        of_key = f'{float(tier.get("of", 0)):.6f}'.rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        of_key = str(tier.get('of', '?'))
    return f'{sd}s/{sc}c/{ratios}r/{of_key}of'


def validate_tier(tier, idx):
    errors = []
    sd = tier.get('sd')
    sc = tier.get('sc')
    ratios = tier.get('ratios', '')
    of_val = tier.get('of')

    if sd is None: errors.append('sd 缺失')
    elif not isinstance(sd, int) or sd < 0: errors.append(f'sd={sd} 无效')

    if sc is None: errors.append('sc 缺失')
    elif not isinstance(sc, int) or sc < 1: errors.append(f'sc={sc} 无效')

    if not ratios: errors.append('ratios 缺失')
    else:
        parts = [p for p in str(ratios).split(',') if p]
        if len(parts) != sc: errors.append(f'sc={sc} 但 ratios 有 {len(parts)} 个值 ({ratios})')
        for p in parts:
            try:
                v = int(p)
                if v < 0: errors.append(f'ratios 含负数 {p}')
            except ValueError:
                errors.append(f'ratios 含非数字 {p}')

    if of_val is not None:
        try:
            of_f = float(of_val)
            if of_f < 0 or of_f > 1: errors.append(f'of={of_val} 超出 0-1 范围')
        except (ValueError, TypeError):
            errors.append(f'of={of_val} 非数字')

    return errors

def validate_tiers(tiers):
    """校验 5 档配置，失败直接抛 ValueError。"""
    if len(tiers) != 5:
        raise ValueError(f'需要5档配置，收到{len(tiers)}')
    for i, t in enumerate(tiers, 1):
        errs = validate_tier(t, i)
        if errs:
            raise ValueError(f'T{i}: {"; ".join(errs)}')

def write_ddc(lv, tiers):
    try:
        validate_tiers(tiers)
    except ValueError as e:
        return False, f'配置校验失败: {e}'
    if len(tiers) != 5:
        return False, f'需要5档配置，收到{len(tiers)}'
    fp = _asset_path(lv)
    ok, msg = verify_integrity(lv)
    if not ok:
        return False, f'写入前: {msg}'
    # 2026-08-04: 记录写入前 mtime——write_ddc 只改 DDC 难度参数，
    # 不更新 mtime，保证 asset mtime 只反映"改关卡配置(牌面)"的时间（时间防线依赖）
    orig_mtime = os.path.getmtime(fp)
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
    # 四元组精确比对
    ok3, msg3 = verify_asset(lv, tiers)
    if not ok3:
        _restore(bak, lv)
        return False, f'四元组比对失败: {msg3}'
    new_sz = os.path.getsize(fp)
    if abs(new_sz - orig_sz) > orig_sz * 0.15:
        _restore(bak, lv)
        return False, f'大小变化({orig_sz}→{new_sz})已回滚'
    _backup_after_write(lv)
    # 2026-08-04: 恢复写入前 mtime（DDC 修改不算关卡配置修改）
    os.utime(fp, (orig_mtime, orig_mtime))
    return True, f'OK ({new_sz}B)'
