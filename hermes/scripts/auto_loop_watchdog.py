"""auto_loop watchdog — 定期检查 auto_loop 健康状态

检查：
1. auto_loop 进程是否存活
2. Unity batch 进程是否存活（auto_loop 在等它时）
3. 日志是否在推进（30 分钟内有无新行）
4. 轮数是否推进（_rounds.json 是否变化）

异常时输出报警信息（供 cron/手动检查），正常输出 OK。
"""
import subprocess, sys, os, json, time

HERMES = r"D:\download\BlastGame\hermes"
AUTOLOG = os.path.join(HERMES, "auto-log")
ROUNDS = os.path.join(HERMES, "project-state", "_rounds.json")

def check():
    issues = []
    # 1. auto_loop 进程
    # 通过日志文件判断 auto_loop 是否活跃（进程名不可靠，多个 python）
    logs = sorted([f for f in os.listdir(AUTOLOG) if f.endswith('.log')], reverse=True)
    if not logs:
        return "⚠ 无 auto_loop 日志"
    latest = os.path.join(AUTOLOG, logs[0])
    mtime = os.path.getmtime(latest)
    age_min = (time.time() - mtime) / 60

    # 2. Unity 进程（tasklist 输出 GBK，bytes 模式拿原始输出再解码）
    r2 = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Unity.exe'], capture_output=True)
    raw = r2.stdout or b''
    unity_alive = 'Unity.exe' in raw.decode('gbk', errors='ignore')

    # 3. 日志推进
    if age_min > 30:
        issues.append(f"⚠ auto_loop 日志 {age_min:.0f} 分钟未更新（{logs[0]}）")

    # 4. 日志内容快照（尾部）
    with open(latest, encoding='utf-8', errors='ignore') as f:
        tail = f.read()[-3000:]
    # 检测关键状态
    if 'FINAL SUMMARY' in tail:
        # 看最终结果
        if 'Passed (入库)' in tail:
            passed_line = [l for l in tail.split('\n') if 'Passed' in l]
            issues.append(f"ℹ auto_loop 已结束: {passed_line[0].strip() if passed_line else '?'}")
        if 'Errors' in tail:
            err_lines = [l for l in tail.split('\n') if '⚠ Errors' in l or 'L85:' in l or 'L119:' in l or 'L120:' in l]
            issues.append(f"⚠ auto_loop 结束但有错误: {'; '.join(e.strip() for e in err_lines[:5])}")
    elif 'Unity batch FAILED' in tail or 'planner FAILED' in tail:
        issues.append("⚠ auto_loop 内部 FAIL 出现（查看日志）")

    # 5. 轮数推进检测（2026-08-10 升级：_rounds.json 半小时无变化 + 日志 30 分钟无更新 = 卡住）
    if os.path.exists(ROUNDS):
        r_mtime = os.path.getmtime(ROUNDS)
        r_age = (time.time() - r_mtime) / 60
        with open(ROUNDS, encoding='utf-8') as f:
            rounds = json.load(f)
        for lv in ['85', '119', '120', '57', '138', '147', '162', '163']:
            rn = rounds.get(lv, 0)
            if rn >= 6:
                issues.append(f"ℹ L{lv} 已达 6 轮上限")
        # auto_loop 活跃但轮数文件超 30 分钟未变 → 可能卡住
        if age_min > 30 and r_age > 30:
            issues.append(f"⚠ 轮数文件 {r_age:.0f} 分钟未变化且日志 {age_min:.0f} 分钟未更新——auto_loop 可能卡住")

    if not issues:
        print(f"OK: auto_loop 活跃（日志 {age_min:.0f} 分钟前更新，Unity={'在跑' if unity_alive else '未跑'}）")
    else:
        print('\n'.join(issues))

if __name__ == '__main__':
    check()