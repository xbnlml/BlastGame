"""重写 board.md：每关单独一行记录"""
import sys, re, json, openpyxl
sys.path.insert(0, r'D:\download\BlastGame\hermes')
from tools.data.adapters import excel_target as et
from tools.data.pool import get_all_records, dedup_records, find_best_monotonic

BOARD = r'D:\download\BlastGame\hermes\project-state\board.md'
XL = r'C:\Users\Administrator\Documents\BlastGame\Doc\手动挑配置记录.xlsx'

# 1. 状态硬编码（从旧 board 已知，避免解析错误）
imported = ['51','52','53','54','55','56','57','58','59','60','61','62','63','64','65','66','67','68','69','70','71','72','73','74','75','76','77','78','79','80','81','82','83','84','85','86','87','88','89','90','91','92','93','94','95','96','97','98','99','100','108','112','124','146','151','153','155','157','158','159','160','161','163','164','168','169','170','171','172','173','174','175','177','178','179','180','181','184','185','186','187','188','190','191','192','193','194','195','196','197','199']
pending = ['136','152','156','162','165','166','167','176','183','189','200']
redesign = {
    '154': '6 轮调优失败，T5=0% 硬违规',
    '182': '6 轮调优失败，T3=46<60',
    '198': '6 轮调优失败，T3=53.8<60',
    '156': '全档 1~5%，极难',
    '166': '上限 50% 连 T1 目标 70 都不到',
    '167': '上限 36% 离目标 90 差 54pp',
    '152': '下限 79% 远高于目标 50（过易）',
    '183': '全档 WR≈8%，极难',
    '189': '下限 70% 远高于目标 50（过易）',
    '200': '全档 7.9%，极难',
}
# 需改关卡中含已入库的移除
for k in list(redesign):
    if k in imported:
        del redesign[k]

# 2. 读 Excel 入库记录（每关最后一组数据=最新）
xl_data = {}
wb = openpyxl.load_workbook(XL, read_only=True)
ws = wb.active
current = None
for row in ws.iter_rows(min_row=2, values_only=True):
    if row and row[0] is not None:
        current = str(row[0])
    if not row or not current:
        continue
    xl_data.setdefault(current, []).append(row)
wb.close()

def excel_latest(lv):
    """Excel 最新一组（有备注的组优先）的 5 档 WR"""
    rows = xl_data.get(lv, [])
    if not rows:
        return None, None, None
    # 分组：备注为空 = 旧记录组；备注非空 = 新记录组（备注可能逐行不同，合并为一个新组）
    groups = []  # [(note, rows)]
    cur = []
    cur_has_note = None
    for r in rows:
        note = r[8] or ''
        has_note = bool(note)
        if cur and has_note != cur_has_note:
            groups.append(cur)
            cur = []
        cur_has_note = has_note
        cur.append(r)
    if cur:
        groups.append(cur)
    # 取最后一组（最新），若为空取最后有备注的组
    latest = groups[-1]
    wrs = []
    for r in latest[:5]:
        wr = r[3]
        wrs.append(round(wr * 100) if wr is not None else None)
    note = latest[0][8] or ''
    return wrs, None, note

# 3. 生成表格行
lines = []
lines.append('# 关卡记录')
lines.append('')
lines.append('**批次：** L51-200（150关）')
lines.append('**最后更新：** 2026-08-04')
lines.append('**事件记录：** `timeline.md`')
lines.append('')
lines.append('> 每关一行，状态变更只改对应行。状态：✅已入库 / 🟡待调优 / 🔴需改关卡')
lines.append('')
lines.append('| 关 | 难度 | 状态 | 入库日期 | 目标 | 最优档位 WR% | 备注 |')
lines.append('|---|---|---|---|---|---|---|')

for lv in range(51, 201):
    key = str(lv)
    # 状态
    if key in imported:
        status = '✅已入库'
    elif key in redesign:
        status = '🔴需改关卡'
    elif key in pending:
        status = '🟡待调优'
    else:
        status = '—'
    # 难度+目标
    t = et.get_target(lv)
    diff = t['diff'] if t else '?'
    targets = '/'.join(str(int(x)) for x in t['tiers']) if t else '?'
    # 最优档位 WR：已入库读 Excel 最新组，其他用池子
    best_wr = '—'
    if key in imported:
        wrs, _, _ = excel_latest(key)
        if wrs and all(w is not None for w in wrs):
            best_wr = '/'.join(str(w) for w in wrs)
        else:
            best_wr = '—'
    else:
        try:
            recs = dedup_records(get_all_records(key))
            ver = [r for r in recs if r.get('source') in ('bot', 'summary', 'phase0')]
            if ver and t:
                combo = find_best_monotonic(ver, t['tiers'], difficulty=diff, top_n=1)
                if combo:
                    wrs = [round(r['wr']) for r in combo[0][2]]
                    best_wr = '/'.join(str(w) for w in wrs)
        except Exception:
            pass
    # 备注（Excel 最新备注）
    _, _, note = excel_latest(key)
    note = note or ''
    if key in redesign:
        note = redesign[key]
    # 入库日期简化：有 Excel 记录的已入库关标 8/4（部分更早）
    date = ''
    if key in imported:
        date = '8/4前'
    lines.append(f'| {lv} | {diff} | {status} | {date} | {targets} | {best_wr} | {note} |')

lines.append('')
lines.append('## 说明')
lines.append('')
lines.append('- 已入库 91 关；待调优 11 关；需改关卡 10 关（L153 已入库，从需改关卡移除）')
lines.append('- 判定标准：`project-state/rules.json`（真源）+ `judge_level.check_judgment()`')
lines.append('- 关卡数据库同步：`tools/leveldb_sync/`（写入 Run/test.json，sourceFileName=hermes-import-*）')

open(BOARD, 'w', encoding='utf-8').write('\n'.join(lines))
print(f'已重写 {BOARD}，共 {len(lines)} 行')
print(f'已入库 {len(imported)} 待调优 {len(pending)} 需改关卡 {len(redesign)}')
