#!/usr/bin/env python3
"""Curator — 跨轮经验积累 Agent

在 auto_loop 跑完后运行：
  1. 读取最新 auto-log 日志
  2. 识别 ≥2 次出现的同类失败
  3. 更新对应 agent 的 memory.md
  4. 输出本轮统计

用法:
  python tools/curator.py                           # 最新日志
  python tools/curator.py --log auto-log/xxx.log    # 指定日志
"""
import argparse, json, os, re, sys
from collections import Counter
from datetime import datetime

HERMES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(HERMES_DIR, 'agents')
LOG_DIR = os.path.join(HERMES_DIR, 'auto-log')


def find_latest_log():
    logs = sorted(
        [f for f in os.listdir(LOG_DIR) if f.endswith('.log')],
        key=lambda f: os.path.getmtime(os.path.join(LOG_DIR, f)),
        reverse=True,
    )
    return os.path.join(LOG_DIR, logs[0]) if logs else None


def parse_log(log_path):
    with open(log_path, encoding='utf-8', errors='replace') as f:
        return f.read()


def detect_patterns(log_text):
    patterns = Counter()
    lines = log_text.split('\n')
    for i, line in enumerate(lines):
        if '不合格' in line:
            # "不合格 — 下一轮(1/6)" — gap 信息在下一行 detail
            if 'T1→T3' in line or 'T3→T5' in line or 'T' in line:
                patterns['gap不足'] += 1
            elif i + 1 < len(lines) and 'gap=' in lines[i + 1]:
                patterns['gap不足'] += 1
            else:
                patterns['不合格(其他)'] += 1
        if 'probe_design_failed' in line:
            patterns['探针设计失败'] += 1
        if 'Unity exited' in line and 'code 0' not in line:
            patterns['Unity异常退出'] += 1
        if 'apply_probes failed' in line:
            patterns['asset写入失败'] += 1
    return patterns


def update_memory(agent, section, content):
    mem_path = os.path.join(AGENTS_DIR, agent, 'memory.md')
    if not os.path.exists(mem_path):
        return False
    with open(mem_path, 'a', encoding='utf-8') as f:
        f.write(f'\n### {datetime.now().strftime("%Y-%m-%d %H:%M")}\n{content}\n')
    return True


# 各 agent memory 的 "自动填充" 区段（curator 负责写）
AUTO_SECTIONS = {
    'planner': '失败探针记录',
    'judge': '边界案例',
    'warden': '最近安全事件',
}


def update_curator_stats(log_text, log_path):
    """在 curator memory 中追加本轮统计"""
    passed = len(re.findall(r'✅.*Passed', log_text))
    failed = len(re.findall(r'❌.*MAX ROUNDS', log_text))
    errors = len(re.findall(r'⚠ Errors:', log_text))
    rounds = re.findall(r'Round (\d+) done:', log_text)
    last_round = rounds[-1] if rounds else '?'
    update_memory('curator', '',
                  f'### 本轮结果\n- 通过入库: {passed}\n- 改关卡: {failed}\n- 错误: {errors}\n- 日志: {os.path.basename(log_path)}')


# ── 监督检查 ──

def supervise(log_text):
    """监督本轮执行合规性。返回违规列表。

    检查项：
      1. 探针是否走了 planner 入口（日志有 planner 调用）
      2. Warden 闸门是否通过（apply_probes 前）
      3. 判定是否用 judge_level（三态结果）
      4. 有没有跳过 agent 直接操作的痕迹
    """
    violations = []

    # 1. planner 被调用（Phase 1 应出现 planner）
    if 'planner.py' not in log_text and 'planner' not in log_text.lower():
        violations.append('探针设计未走 planner 入口')

    # 2. Warden 闸门（Phase 3 前应有 Warden 检查）
    if 'warden' not in log_text.lower():
        violations.append('批跑前未执行 Warden 检查')
    elif 'Warden 通过' not in log_text and 'WARDEN' not in log_text:
        violations.append('Warden 检查无通过记录')

    # 3. 判定三态（Phase 5 应有 合格/接近/不合格）
    if '合格' not in log_text and '不合格' not in log_text:
        violations.append('未发现判定结果（合格/不合格）')

    # 4. apply_probes Warden 闸门（写入前）
    if 'Warden BLOCKED' in log_text:
        violations.append('本轮有探针被 Warden 打回（探针质量不合格）')

    # 5. 阶段时序验证（Phase 1→3→5 顺序）
    phases = re.findall(r'Phase (\d)', log_text)
    if phases:
        expected = ['1', '3', '5']
        actual = [p for p in phases if p in expected]
        if actual and actual != ['1', '3', '5'] and actual != ['1', '2', '3', '4', '5']:
            violations.append(f'阶段顺序异常: {actual}')
    
    # 6. Curator 自己（memory 更新）
    if 'MAX ROUNDS' in log_text and '改关卡' not in log_text:
        violations.append('6轮上限触发但无改关卡标记')

    return violations


def main():
    parser = argparse.ArgumentParser(description='Curator — 跨轮经验积累')
    parser.add_argument('--log', help='auto-log 日志路径')
    args = parser.parse_args()

    log_path = args.log or find_latest_log()
    if not log_path or not os.path.exists(log_path):
        print('No log found')
        return

    log_text = parse_log(log_path)
    patterns = detect_patterns(log_text)

    print(f'Curator: analyzing {os.path.basename(log_path)}')

    # ── 监督检查 ──
    violations = supervise(log_text)
    if violations:
        print('监督报告 — 违规项:')
        for v in violations:
            print(f'  ⛔ {v}')
        update_memory('warden', '最近安全事件',
                      f'- 监督发现违规: {"; ".join(violations)}')
    else:
        print('监督报告 — ✅ 全部合规')

    print('Patterns found:')
    for pat, count in patterns.most_common():
        if count >= 2:
            print(f'  🔴 {pat}: {count}次 → 写入对应 agent memory')
            if 'gap' in pat:
                update_memory('judge', '边界案例',
                              f'- 本轮出现 {count} 次 gap不足: {pat}')
            if '探针' in pat:
                update_memory('planner', '失败探针记录',
                              f'- 本轮 {count} 次探针设计失败')
            if 'Unity' in pat:
                update_memory('warden', '最近安全事件',
                              f'- 本轮 {count} 次 Unity异常退出')
        else:
            print(f'  ⚪ {pat}: {count}次 (未达阈值)')

    update_curator_stats(log_text, log_path)
    print('Curator memory updated')


if __name__ == '__main__':
    main()
