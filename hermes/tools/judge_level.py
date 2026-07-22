"""关卡现存数据评判工具

注：跨档枚举核心逻辑已迁移至 tools/find_best_combo.py。
    判定逻辑已迁移至 tools/validate_combo.py。
    本脚本保留为便捷前端，底层调用上述工具。

用法:
  python judge_level.py 57                # 单关评判
  python judge_level.py 57,64,80          # 多关
  python judge_level.py 52-100            # 范围
  python judge_level.py --scan 51-100     # 扫描状态（输出分类表）
"""
import sys, os, json
from collections import defaultdict

REPO = r'C:\Users\Administrator\Documents\BlastGame'
PROGRESS_PATH = os.path.join(os.path.dirname(__file__), '../project-state/progress.json')
STAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stage-data')

# ===== 难度判定辅助 =====
def get_difficulty(lv):
    """从 asset 读难度"""
    apath = os.path.join(REPO, f'Assets/GameModule/GameMain/ConfigSo/Generated_enum/test/{lv}.asset')
    if not os.path.isfile(apath):
        return 'Unknown'
    with open(apath, 'r', encoding='utf-8') as f:
        c = f.read()
    import re
    m = re.search(r'difficultyLevel:\s*(\d+)', c)
    if m:
        return {0:'Normal', 1:'Hard', 2:'SuperHard'}.get(int(m.group(1)), 'Unknown')
    return 'Unknown'

# ===== 数据检索 =====
def load_stage_data(levels):
    """从 stage-data 加载数据，返回 {lv: [records]}。

    stage-data 是 get_level_pool 刷出的缓存，格式：
      [{'wr', 'sd', 'sc', 'ratios', 'of', 'totalGames', 'tier', 'source'}, ...]
    """
    result = {}
    for lv in levels:
        lv_s = str(lv)
        fp = os.path.join(STAGE_DIR, lv_s, f'{lv_s}.json')
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        records = data.get('reliable', []) + data.get('reference', [])
        if records:
            result[lv_s] = records
    return result

# ===== 规则检查(judgment-rules.md ②③④⑤) =====
def check_judgment(combo, diff):
    """combo: {'T1':wr, 'T2':wr, 'T3':wr, 'T4':wr, 'T5':wr}
    返回 (passed, reasons)"""
    reasons = []
    wrs = [combo.get(f'T{i}', 0) for i in range(1,6)]
    
    gaps = []
    for i in range(4):
        g = wrs[i] - wrs[i+1]
        gaps.append(g)
    
    # 硬性违规
    hard_fail = False
    # Normal: T2=T1, T4=T5, 所以只检查 T1->T3(idx=1) 和 T3->T5(idx=2)
    # Hard/SuperHard: 检查全部 4 个 gap
    check_indices = [1, 2] if diff == 'Normal' else [0, 1, 2, 3]
    for i in check_indices:
        g = gaps[i]
        if g < 5:
            reasons.append(f'!! HARD: T{i+1}->T{i+2} gap={g:.1f}% < 5%')
            hard_fail = True
        if g > 40:
            reasons.append(f'!! HARD: T{i+1}->T{i+2} gap={g:.1f}% > 40%')
            hard_fail = True
    
    for i in check_indices:
        if wrs[i] < wrs[i+1] - 1:
            reasons.append(f'!! HARD: T{i+1}={wrs[i]:.1f}% < T{i+2}={wrs[i+1]:.1f}% (inverted)')
            hard_fail = True
    
    t3 = wrs[2]
    if diff == 'Normal' and t3 < 60:
        reasons.append(f'!! HARD: Normal T3={t3:.1f}% < 60%')
        hard_fail = True
    elif diff == 'Hard' and (t3 < 30 or t3 > 60):
        reasons.append(f'!! HARD: Hard T3={t3:.1f}% not in 30-60%')
        hard_fail = True
    elif diff == 'SuperHard' and t3 > 50:
        reasons.append(f'!! HARD: SuperHard T3={t3:.1f}% > 50%')
        hard_fail = True
    
    if any(w < 5 for w in wrs):
        reasons.append('!! HARD: Some tier WR < 5%')
        hard_fail = True
    
    for i in check_indices:
        expected = 15 if diff == 'Normal' else 10
        g = gaps[i]
        if g < expected:
            reasons.append(f'!! T{i+1}->T{i+2} gap={g:.1f}% < recommended {expected}%')
    
    for i in check_indices:
        g = gaps[i]
        wr_max = max(wrs[i], wrs[i+1])
        if wr_max > 50:
            if not (15 <= g <= 35):
                reasons.append(f'!! Aesthetic: T{i+1}->T{i+2} gap={g:.1f}% outside 15-35pp (>50% segment)')
        else:
            if not (5 <= g <= 25):
                reasons.append(f'!! Aesthetic: T{i+1}->T{i+2} gap={g:.1f}% outside 5-25pp (<50% segment)')
    
    # 档差递减检查：Normal只看T1->T3和T3->T5
    if diff == 'Normal':
        if len(check_indices) >= 2 and gaps[check_indices[0]] < gaps[check_indices[1]] - 4:
            reasons.append(f'!! Aesthetic: T1->T3({gaps[1]:.1f}) < T3->T5({gaps[2]:.1f}) gap not descending')
    else:
        for i in range(3):
            if gaps[i] < gaps[i+1] - 4:
                reasons.append(f'!! Aesthetic: T{i+1}->T{i+2}({gaps[i]:.1f}) < T{i+2}->T{i+3}({gaps[i+1]:.1f}) gap not descending')
    
    if hard_fail:
        return '不合格', reasons
    if any('gap=' in r and '< recommended' in r for r in reasons):
        return '接近', reasons
    return '合格', reasons

def find_best_combo(data_records, diff):
    """从数据记录中找最佳五档组合。对 Normal 只需 T1,T3,T5 三档(T2=T1,T4=T5)"""
    # 按 WR 排序
    sorted_recs = sorted(data_records, key=lambda x: x['wr'], reverse=True)
    
    if diff == 'Normal':
        # Normal: T2=T1, T4=T5. 需要找3个不同配置(按四元组去重)
        # 优先使用带 tier 标记的 opt 数据
        opt_t1 = [r for r in sorted_recs if r.get('tier') == 'T1' and r['wr'] > 0]
        opt_t3 = [r for r in sorted_recs if r.get('tier') == 'T3' and r['wr'] > 0]
        opt_t5 = [r for r in sorted_recs if r.get('tier') == 'T5' and r['wr'] > 0]
        
        # 按配置去重（同sd/sc/ratios/of算同一个配置）
        def unique_by_cfg(recs, relax=False):
            """按配置去重。relax=True 时忽略 sd（sc/ratios/of 即视为同一配置族）"""
            seen = set()
            out = []
            for r in recs:
                if relax:
                    k = (r.get('sc',''), r.get('ratios',''), r.get('of',''))
                else:
                    k = (r.get('sd',''), r.get('sc',''), r.get('ratios',''), r.get('of',''))
                if k not in seen:
                    seen.add(k)
                    out.append(r)
            return out
        
        def ensure_min(recs, n=3):
            """确保候选 >= n 个。

            优先级：
              1. 严格去重 (sd,sc,ratios,of) — 够 n 个就返回
              2. 放宽去重 (sc,ratios,of, 忽略 sd) — 同族不同档位
              3. 不去重，取前 10 条（多批次自然有不同 WR 值）
            """
            strict = unique_by_cfg(recs, relax=False)
            if len(strict) >= n:
                return strict
            relaxed = unique_by_cfg(recs, relax=True)
            if len(relaxed) >= n:
                return relaxed
            # 最后兜底：不同 bot 批次即使配置完全一样也会 wr 不同
            return recs[:10]
        
        t1_cands = ensure_min(opt_t1, 3) if opt_t1 else ensure_min(sorted_recs[:10], 3)
        t3_cands = ensure_min(opt_t3, 3) if opt_t3 else ensure_min(sorted_recs, 3)
        t5_cands = ensure_min(opt_t5, 3) if opt_t5 else ensure_min(sorted_recs, 3)
        
        best = None
        best_score = -1
        for t1_rec in t1_cands:
            for t3_rec in t3_cands:
                if t3_rec['wr'] >= t1_rec['wr']:
                    continue
                for t5_rec in t5_cands:
                    if t5_rec['wr'] >= t3_rec['wr']:
                        continue
                    combo = {
                        'T1': t1_rec['wr'], 'T2': t1_rec['wr'],
                        'T3': t3_rec['wr'], 'T4': t5_rec['wr'], 'T5': t5_rec['wr']
                    }
                    result, reasons = check_judgment(combo, diff)
                    if '不合格' in result:
                        continue
                    wrs = [combo[f'T{i}'] for i in range(1,6)]
                    gaps = [wrs[i]-wrs[i+1] for i in range(4)]
                    score = sum(gaps) - sum(abs(g-20) for g in gaps)
                    if score > best_score:
                        best_score = score
                        best = (combo, result, reasons)
        if best:
            return best
        # Fallback: 没带tier标记的数据，直接按WR选3个不同值
        seen_wrs = set()
        uniq = []
        for r in sorted_recs:
            w = int(r['wr'])
            if w not in seen_wrs:
                seen_wrs.add(w)
                uniq.append(r)
        if len(uniq) >= 3:
            t1, t3, t5 = uniq[0], uniq[len(uniq)//2], uniq[-1]
            if t1['wr'] > t3['wr'] > t5['wr']:
                combo = {'T1':t1['wr'],'T2':t1['wr'],'T3':t3['wr'],'T4':t5['wr'],'T5':t5['wr']}
                result, reasons = check_judgment(combo, diff)
                if '不合格' not in result:
                    return (combo, result, reasons)
        return (None, '不合格', ['无法从现有数据拼出合格组合'])
    
    else:  # Hard/SuperHard: 5 档独立
        best = None
        best_score = -1
        # 5 层循环太多，先按 tier 分组
        tier_recs = {'T1':[], 'T2':[], 'T3':[], 'T4':[], 'T5':[]}
        for rec in sorted_recs:
            tn = rec.get('tier', '')
            if tn in tier_recs:
                tier_recs[tn].append(rec)
        
        # 如果没 tier 标记，按 WR 段分
        all_tiers = any(tier_recs[t] for t in tier_recs if t in ['T1','T2'])
        if all_tiers and all(len(tier_recs[t]) > 0 for t in ['T1','T2','T3','T4','T5']):
            for t1 in tier_recs['T1'][:5]:
                for t2 in tier_recs['T2'][:5]:
                    if t2['wr'] >= t1['wr']: continue
                    for t3 in tier_recs['T3'][:5]:
                        if t3['wr'] >= t2['wr']: continue
                        for t4 in tier_recs['T4'][:5]:
                            if t4['wr'] >= t3['wr']: continue
                            for t5 in tier_recs['T5'][:5]:
                                if t5['wr'] >= t4['wr']: continue
                                combo = {
                                    'T1': t1['wr'], 'T2': t2['wr'],
                                    'T3': t3['wr'], 'T4': t4['wr'], 'T5': t5['wr']
                                }
                                result, reasons = check_judgment(combo, diff)
                                if '不合格' in result:
                                    continue
                                wrs = [combo[f'T{i}'] for i in range(1,6)]
                                gaps = [wrs[i]-wrs[i+1] for i in range(4)]
                                score = sum(gaps) - sum(abs(g-15) for g in gaps)
                                if score > best_score:
                                    best_score = score
                                    best = (combo, result, reasons)
        
        if not best:
            # 无 tier 标记，按 WR 降序直接选 5 个不同配置
            uniq = []
            seen = set()
            for r in sorted_recs:
                k = (r['wr'], r.get('sd',''), r.get('sc',''))
                if k not in seen:
                    seen.add(k)
                    uniq.append(r)
            if len(uniq) >= 5:
                t1, t2, t3, t4, t5 = uniq[:5]
                combo = {'T1':t1['wr'], 'T2':t2['wr'], 'T3':t3['wr'], 'T4':t4['wr'], 'T5':t5['wr']}
                result, reasons = check_judgment(combo, diff)
                best = (combo, result, reasons)
        
        return best if best else (None, '!!不合格', ['无法从现有数据拼出合格组合'])

# ===== --scan 模式 =====
def scan_mode(levels):
    """Scan level status, output classification table"""
    # Load progress.json
    pj = {}
    if os.path.isfile(PROGRESS_PATH):
        with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
            pj = json.load(f)
    
    status_map = pj.get('status', {})
    stage_data = load_stage_data(levels)
    
    print("=" * 75)
    print(" Level Status Scan (stage-data)")
    print("=" * 75)
    print(f"{'Lv':>4} {'Diff':<10} {'Status':<8} {'#cfg':>5} {'rel':>4} {'ref':>4} {'span':>6} {'BestCombo'}")
    print('-' * 75)
    
    for lv_s in levels:
        diff = get_difficulty(lv_s)
        status = status_map.get(lv_s, 'unknown')
        
        records = stage_data.get(lv_s, [])
        
        n_total = len(records)
        n_rel = sum(1 for r in records if r.get('source') != 'phase1')
        n_ref = sum(1 for r in records if r.get('source') == 'phase1')
        
        span = 0.0
        combo_str = '-'
        if records:
            wrs = [r['wr'] for r in records]
            span = max(wrs) - min(wrs)
            combo, result, _ = find_best_combo(records, diff)
            if combo:
                combo_str = f"{result} {combo['T1']:.0f}->{combo['T3']:.0f}->{combo['T5']:.0f}"
            else:
                combo_str = 'none'
        
        status_s = status[:6] if len(status) > 6 else status
        print(f"L{lv_s:>3} {diff:<10} {status_s:<8} {n_total:>5} {n_rel:>4} {n_ref:>4} {span:>5.1f} {combo_str}")
    
    print('-' * 75)
    done = [lv for lv, st in status_map.items() if st == 'done']
    verify_lvs = [lv for lv, st in status_map.items() if st == 'verify']
    probe_lvs = [lv for lv, st in status_map.items() if st == 'probe']
    print(f"done: {len(done)} | verify: {len(verify_lvs)} | probe: {len(probe_lvs)}")

# ===== 入口 =====
def parse_levels(spec):
    levels = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            for lv in range(int(a), int(b)+1):
                levels.add(str(lv))
        else:
            levels.add(part)
    return sorted(levels, key=int)

def main():
    if len(sys.argv) < 2:
        print("用法: python judge_level.py <levels>")
        print("       python judge_level.py --scan <range>")
        sys.exit(1)
    
    if sys.argv[1] == '--scan':
        if len(sys.argv) > 2:
            scan_mode(parse_levels(sys.argv[2]))
        else:
            scan_mode([str(i) for i in range(51, 101)])
        return
    
    levels = parse_levels(sys.argv[1])
    
    # 加载数据 (从 stage-data 缓存)
    stage_data = load_stage_data(levels)
    
    print(f"={'='*70}")
    print(f" L51-100 现有数据评判 (stage-data)")
    print(f"={'='*70}")
    
    for lv_s in levels:
        diff = get_difficulty(lv_s)
        print(f"\n--- L{lv_s} ({diff}) ---")
        
        records = stage_data.get(lv_s, [])
        
        if not records:
            print(f"  !! 无数据 (stage-data 中不存在 L{lv_s})")
            continue
        
        wrs = [r['wr'] for r in records]
        n_rel = sum(1 for r in records if r.get('source') != 'phase1')
        n_ref = sum(1 for r in records if r.get('source') == 'phase1')
        span = max(wrs) - min(wrs)
        
        print(f"  数据: {len(records)}配置 (rel={n_rel}, ref={n_ref}), span={span:.1f}pp")
        
        # ⑥预判：有可靠数据才判 span
        pre = ''
        if n_rel > 0:
            if span >= 25:
                pre = '可跑'
            elif span >= 15:
                pre = '可疑(限2轮)'
            else:
                pre = '改关卡'
        else:
            pre = '无可靠数据，暂不判'
        print(f"  ⑥预判: {pre}")
        
        # 找最佳组合
        combo, result, reasons = find_best_combo(records, diff)
        
        if combo:
            wrs_s = '->'.join(f"{combo[f'T{i}']:.1f}%" for i in range(1,6))
            gaps_s = '->'.join(f"{combo[f'T{i}']-combo[f'T{i+1}']:.1f}" for i in range(1,5))
            print(f"  >> {result}  T1->T5: {wrs_s}")
            print(f"     档差: {gaps_s}pp")
        else:
            print(f"  !! 无合格组合")
        
        for r in reasons[:5]:
            print(f"    {r}")

if __name__ == '__main__':
    main()
