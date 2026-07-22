#!/usr/bin/env python3
"""51-100 状态汇总工具

用法:
  python tools/stage_status.py              # 全部
  python tools/stage_status.py --simple      # 一行汇总
  python tools/stage_status.py 51,55,60      # 指定关卡
"""
import sys, os, json
from collections import defaultdict

STAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stage-data')
PROGRESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'project-state', 'progress.json')
TARGETS = r'C:\Users\Administrator\Documents\BlastGame\Assets\LvEditorConfig\lv_win_config_test.xlsx'
from openpyxl import load_workbook
import re

def get_difficulty_map():
    m = {}
    try:
        wb = load_workbook(TARGETS, data_only=True)
        ws = wb.active
        for r in range(2, ws.max_row+1):
            try:
                lv = str(int(ws.cell(r,1).value))
                diff = str(ws.cell(r,9).value or '').lower()
                m[lv] = diff
            except: pass
    except: pass
    return m

def get_summary():
    sp = os.path.join(STAGE_DIR, '_summary.json')
    if os.path.exists(sp):
        return json.load(open(sp))
    return {}

def main():
    diffs = get_difficulty_map()
    summary = get_summary()
    
    progress = {}
    if os.path.exists(PROGRESS):
        progress = json.load(open(PROGRESS))
    
    simple = '--simple' in sys.argv
    
    levels = [str(i) for i in range(51, 101)]
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        spec = sys.argv[1]
        levels = []
        for part in spec.split(','):
            if '-' in part:
                a,b = part.split('-')
                levels.extend(str(i) for i in range(int(a), int(b)+1))
            else:
                levels.append(part)
    
    done, need_tuning, no_data = [], [], []
    for lv in sorted(levels, key=int):
        if lv in progress and isinstance(progress[lv], dict) and progress[lv].get('status') == 'done':
            done.append(lv)
        elif lv in progress and isinstance(progress[lv], dict) and progress[lv].get('status') == 'need_tuning':
            need_tuning.append(lv)
        else:
            no_data.append(lv)
    
    if simple:
        print(f'Done={len(done)}  Tuning={len(need_tuning)}  NoData={len(no_data)}  Total={len(levels)}')
        return
    
    print(f'51-100 状态汇总 ({len(levels)}关)')
    print('=' * 50)
    
    if done:
        print(f'\n完成 ({len(done)}):')
        for lv in done:
            d = diffs.get(lv, '?')
            s = summary.get('levels', {}).get(lv, {})
            bot_n = s.get("sources",{}).get("bot",0)
            span_s = s.get("wr_span","?")
            print("  %s (%s) bot=%s span=%s" % (lv.rjust(3), d.rjust(8), bot_n, span_s))
        print(f'\n待处理 ({len(need_tuning)}):')
        for lv in need_tuning:
            d = diffs.get(lv, '?')
            s = summary.get('levels', {}).get(lv, {})
            bot_n = s.get("sources",{}).get("bot",0)
            span_s = s.get("wr_span","?")
            print("  %s (%s) bot=%s span=%s" % (lv.rjust(3), d.rjust(8), bot_n, span_s))
        print(f'\n无数据 ({len(no_data)}):')
        for lv in no_data:
            d = diffs.get(lv, '?')
            print(f'  L{lv:>3s} ({d:>8})')

if __name__ == '__main__':
    main()
