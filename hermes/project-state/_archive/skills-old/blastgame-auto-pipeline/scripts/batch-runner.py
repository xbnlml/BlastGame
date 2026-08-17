#!/usr/bin/env python3
"""批B机械执行器 — 逐关 patch → focus → submit → poll → next"""
import json, os, time, glob, csv, re, subprocess, sys
REPO = r"C:\Users\Administrator\Documents\BlastGame"
LOG = os.path.join(REPO, "BuildLogs/batch-runner.log")
log = open(LOG, 'w', encoding='utf-8')
def echo(m): print(m, flush=True); log.write(m+"\n"); log.flush()
def focus():
    subprocess.Popen(['powershell','-NoProfile','-Command',
        '(New-Object -ComObject WScript.Shell).AppActivate("BlastGame")|Out-Null'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
R1 = {'sd':[1,5,10,20,30],'sc':[5,5,4,5,5],
      'rat':["1,1,1,1,1","1,1,1,1,1","1,1,1,1","10,1,1,1,1","10,1,1,1,10"],
      'of':[0.5]*5}

def submit_and_wait(lv, tag):
    req = os.path.join(REPO,'BuildLogs/auto-batch-request.json')
    if os.path.exists(req): os.remove(req)
    json.dump({'levelSpec':str(lv),'runCount':200,'levelFolder':'test',
        'tiersCsv':'1,2,3,4,5','recordReplay':False,'tag':tag}, open(req,'w'))
    echo(f"  submitted {tag}")
    for i in range(120):
        time.sleep(1)
        if not os.path.exists(req): return True
    focus(); time.sleep(60)
    if not os.path.exists(req): return True
    d=json.load(open(req)); os.remove(req); time.sleep(3)
    json.dump(d,open(req,'w'))
    for i in range(120):
        time.sleep(1)
        if not os.path.exists(req): return True
    echo(f"  STUCK → restart Unity")
    subprocess.run(['taskkill','/F','/IM','Unity.exe'], capture_output=True)
    time.sleep(5)
    subprocess.Popen(['C:/Program Files/Unity/Hub/Editor/6000.0.60f1/Editor/Unity.exe','-projectPath',REPO],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return False

def poll_export(lv, timeout=600):
    start = time.time()
    while time.time()-start < timeout:
        time.sleep(5)
        for d in sorted(glob.glob(os.path.join(REPO,f"telemetry/bot/{lv}-{lv}-*/*-range/"))):
            m=re.search(r'T(\d+)',os.path.basename(d))
            if not m: continue
            for sf in glob.glob(os.path.join(d,"campaign-summary-*.csv")):
                if os.path.getsize(sf)>50:
                    return True
    return False

pp = os.path.join(REPO, "BuildLogs/pipeline-progress.json")
with open(pp) as f: p = json.load(f)
pending = [str(lv) for lv in range(57,101)
    if str(lv) not in p['levels']['done'] and str(lv) not in p['levels']['改关卡']]
echo(f"Pending: {len(pending)} levels: {pending}")

for i, lv_s in enumerate(pending):
    lv=int(lv_s); echo(f"\n[{i+1}/{len(pending)}] L{lv}")
    fp = os.path.join(REPO,f"Assets/GameModule/GameMain/ConfigSo/Generated_enum/test/{lv}.asset")
    nb = "    DynamicDifficultyConfigs:\n"
    for j in range(5):
        nb += f"    - StartDifficulty: {R1['sd'][j]}\n      ShuffleSplitCount: {R1['sc'][j]}\n      ShuffleSplitRatios: {R1['rat'][j]}\n      ShuffleOverflowFactor: {R1['of'][j]}\n"
    with open(fp) as f: c = f.read()
    old = re.search(r"    DynamicDifficultyConfigs:.*?(?=\n    [a-z]|\Z)", c, re.DOTALL)
    if old: c = c[:old.start()] + nb + c[old.end():]
    with open(fp,'w') as f: f.write(c)
    echo(f"  patched")
    focus(); time.sleep(30)
    ok = submit_and_wait(lv, f"l{lv}-r1")
    if not ok:
        with open(pp) as f: p=json.load(f)
        p['levels']['改关卡'].append(lv_s)
        with open(pp,'w') as f: json.dump(p,f,indent=2)
        echo(f"  FAILED → 改关卡"); continue
    ok = poll_export(lv)
    echo(f"  {'✅ export found' if ok else '⏰ TIMEOUT → 改关卡'}")
    with open(pp) as f: p=json.load(f)
    if not ok:
        p['levels']['改关卡'].append(lv_s)
    elif lv_s not in p['levels']['done']:
        p['levels']['done'].append(lv_s)
    for k in ['pending_51_70','pending_71_100']:
        if lv_s in p['levels'].get(k,[]): p['levels'][k].remove(lv_s)
    with open(pp,'w') as f: json.dump(p,f,indent=2)
echo(f"\n=== DONE ===")
with open(pp) as f: p=json.load(f)
echo(f"Done: {len(p['levels']['done'])} 改关卡: {len(p['levels']['改关卡'])}")
log.close()
