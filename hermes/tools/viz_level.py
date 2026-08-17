#!/usr/bin/env python3
"""关卡调优数据可视化工具

用法:
  python tools/viz_level.py 72              # 单关 5 档 WR vs sd
  python tools/viz_level.py 51-100          # 多关 span 分布
  python tools/viz_level.py 72 --html       # 输出 HTML 文件
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stage-data')
TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools')


def parse_levels(spec):
    levels = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            for lv in range(int(a), int(b) + 1):
                levels.append(lv)
        else:
            levels.append(int(part))
    return levels


def load_pool(lv):
    fp = os.path.join(STAGE_DIR, str(lv), f'{lv}.json')
    if not os.path.exists(fp):
        return None
    with open(fp) as f:
        return json.load(f)


def plot_level(lv, output_html=False):
    """画单关的 WR vs sd 散点图"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    d = load_pool(lv)
    if not d:
        print(f'L{lv}: 无数据')
        return

    rel = d.get('reliable', [])
    if not rel:
        print(f'L{lv}: 无可靠数据')
        return

    # 按 tier 分组
    tiers = {}
    for r in rel:
        t = r.get('source_tier', r.get('tier', '')).split('-')[0]
        if t.startswith('T'):
            tiers.setdefault(t, []).append(r)

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=(f'L{lv} WR vs sd', f'L{lv} WR 分布'),
                        column_widths=[0.6, 0.4])

    colors = {'T1': '#1f77b4', 'T2': '#ff7f0e', 'T3': '#2ca02c',
              'T4': '#d62728', 'T5': '#9467bd'}

    all_wrs = []
    for t in sorted(tiers.keys()):
        pts = tiers[t]
        sds = [float(p.get('sd', 0)) for p in pts]
        wrs = [p['wr'] for p in pts]
        all_wrs.extend(wrs)
        fig.add_trace(go.Scatter(
            x=sds, y=wrs, mode='markers',
            name=t, marker=dict(color=colors.get(t, '#333'), size=6),
            text=[f"sd={s}<br>sc={p.get('sc','?')}<br>ratios={p.get('ratios','?')}<br>of={p.get('of','?')}"
                  for s, p in zip(sds, pts)],
            hoverinfo='text'), row=1, col=1)

    # WR 分布直方图
    if all_wrs:
        fig.add_trace(go.Histogram(x=all_wrs, nbinsx=20, name='WR分布'), row=1, col=2)

    fig.update_layout(height=500, title_text=f'L{lv} 调优数据', showlegend=True)
    fig.update_xaxes(title_text='sd', row=1, col=1)
    fig.update_yaxes(title_text='WR (%)', row=1, col=1)

    if output_html:
        fp = f'L{lv}_viz.html'
        fig.write_html(fp)
        print(f'✅ 已输出 {fp}')
    else:
        fig.show()


def plot_span(levels, output_html=False):
    """画多关的 span 分布"""
    import plotly.graph_objects as go

    lv_list = []
    spans = []
    counts = []
    labels = []

    for lv in levels:
        d = load_pool(lv)
        if not d:
            continue
        rel = d.get('reliable', [])
        wrs = sorted(set(r['wr'] for r in rel))
        span = round(wrs[-1] - wrs[0], 1) if len(wrs) >= 2 else 0
        lv_list.append(lv)
        spans.append(span)
        counts.append(len(rel))
        labels.append(f'L{lv}<br>{len(rel)}条<br>span={span}pp')

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=lv_list, y=spans,
        text=[f'{s}pp' for s in spans],
        textposition='outside',
        marker_color=['green' if s >= 25 else 'orange' if s >= 15 else 'red' for s in spans],
        hovertemplate='%{text}<extra></extra>'
    ))

    fig.add_hline(y=25, line_dash='dash', line_color='green', annotation_text='span≥25')
    fig.add_hline(y=15, line_dash='dash', line_color='orange', annotation_text='span≥15')

    fig.update_layout(
        title='关卡 span 分布',
        xaxis_title='关卡',
        yaxis_title='span (pp)',
        height=500,
    )

    if output_html:
        fp = 'span_distribution.html'
        fig.write_html(fp)
        print(f'✅ 已输出 {fp}')
    else:
        fig.show()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    spec = sys.argv[1]
    html = '--html' in sys.argv

    levels = parse_levels(spec)

    if len(levels) == 1:
        plot_level(levels[0], html)
    else:
        plot_span(levels, html)


if __name__ == '__main__':
    main()
