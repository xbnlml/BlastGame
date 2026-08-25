#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slim_blastgame_skill.py — blastgame SKILL.md 瘦身迁移工具（安全：默认 dry-run）

把 blastgame SKILL.md 从 ~166KB 压到 ~52KB：
  1. 常见坑速查 (L451-589, 68KB) -> references/pitfalls.md
  2. 七个重段 -> references 摘要 stub（人工补摘要）
  3. References 索引 15.5KB -> 2.5KB 精简版 + 指向 INDEX.md
  4. 顶部 2026-08-11/12 日志压缩为 1 行

用法（从项目 hermes/ 目录跑）：
  python scripts/slim_blastgame_skill.py            # dry-run，只输出产物到工作区并打印尺寸
  python scripts/slim_blastgame_skill.py --apply    # 备份后写入真实 skill 目录

产物：
  dry-run:  <workdir>/_slim_draft/SKILL.md（新主文件草稿）+ pitfalls.md（坑表草稿）
  --apply:  直接写回 skill 目录（先备份 SKILL.md.bak-<date>）
"""
import os, re, shutil, sys, datetime
from pathlib import Path

_local_app_data = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
_hermes_home = Path(os.environ.get('HERMES_HOME', _local_app_data / 'hermes'))
SKILL_DIR = str(_hermes_home / 'skills' / 'game-design' / 'blastgame')
SKILL = os.path.join(SKILL_DIR, "SKILL.md")
REFS  = os.path.join(SKILL_DIR, "references")

# ---- 段边界（1-indexed 行号，基于 2026-08-14 实测）----
# (start, end, kind, title)
# kind: 'move' 整段外移成 reference；'stub' 留 1.1KB 摘要占位；'drop' 直接删（有指向）
SECTIONS = [
    (256, 313, "stub", "数据可靠性（pool）",          "references/pool-data-reliability-20260814.md"),
    (389, 414, "stub", "用户沟通铁则",                "references/user-communication-rules-20260814.md"),
    (422, 440, "stub", "DDA 运行时参数（概要）",       "references/dda-runtime.md"),
    (441, 450, "drop", "工具链修复精华（指向 tool-fixes.md）", "references/tool-fixes.md"),
    (451, 589, "move", "常见坑速查",                  "references/pitfalls.md"),
    (590, 628, "stub", "入库落盘（asset+Excel+board+LevelDatabase）", "references/reimport-write-down-20260814.md"),
    (629, 644, "stub", "只读现状查询",                "scripts/level_status.py"),
]

STUB_TEMPLATE = """
## {title}（摘要 · 详见 {target}）

> 移出历史：本段原在 SKILL.md L{start}-L{end}（{size}KB），为瘦身外移。
> 核心规则速览（TODO：由人工从原文提炼 ≤1KB 后替换本占位）：
> - 规则1：……
> - 规则2：……
"""

SLIM_REFS_INDEX = """## References（精简速查）

> 完整索引（90+ 文件按主题分组）见 `references/INDEX.md`。本表只列**每次开工必用**的核心文件：

| 文件 | 何时读 |
|------|--------|
| `references/pitfalls.md` | 遇坑/症状排查（配上方「坑速查」症状索引） |
| `references/probe-efficiency-standards-20260806.md` | 探针设计铁则总纲 |
| `references/leveldb-compare-match-20260808.md` | DB 匹配/compare_level_db |
| `references/bot400-vs-db-consistency-20260810.md` | bot400 vs DB 一致性 |
| `references/optimizer-vs-bot-neutral-tier-rootcause-20260812.md` | 优化器 vs bot400 胜率差根因 |
| `references/tool-fixes.md` | 工具链修复全记录 |
| `references/mtime-fence-automation-20260804.md` | 时间防线 |
| `references/pool-board-filter-final-20260804.md` | 池子牌面校验第六代定稿 |
| `references/tool-first-20260814.md` | 工具优先触发清单 |
| `scripts/level_status.py` / `scripts/pool_gap_analysis.py` / `scripts/skeleton_enum.py` | 只读/分析脚本 |

其余主题一律先查 `references/INDEX.md`（A-I 分组）再读对应文件。
"""

SYMPTOM_INDEX_TEMPLATE = """## 坑速查（症状 → 查 references/pitfalls.md 锚点）

> 完整 132 条坑见 `references/pitfalls.md`（按域分锚点）。下表是**症状触发索引**：
> 遇到症状 → 找关键词行 → 跳对应锚点。找不到 → 直接读 pitfalls.md 全文。

| 症状关键词 | 查 pitfalls.md 锚点 |
|-----------|--------------------|
| 判定分档 / flat 10pp / Hard SuperHard 合格线 | #judgment |
| gap 接近线 / 容差 / 目标偏差 | #judgment |
| phase1 phase2 数据 / filter_verified / 数据源优先级 | #data-source |
| 同配置胜率差大 / dedup 埋数据 / 关卡被改 | #data-source |
| 时间防线 / 快照 / mtime / 批次目录 | #data-source |
| 探针设计 / 反推法 / sd 方向 / ratios | #probe |
| 探针打空 / 组合不变 / 6轮白跑 | #probe |
| auto_loop 超时 / planner FAILED / sys.path / ModuleNotFoundError | #auto-loop |
| 轮次 / inc_round / 双增 / MAX ROUNDS | #auto-loop |
| DB 白关 / fingerprint / resolveActiveRun / 单档 entry | #leveldb |
| Excel 单位 / 小数 / 百分数 / 就地更新 / 追加 | #write-down |
| board 行更新 / 正则列错位 / 每关一行 | #write-down |
| 贝叶斯提前停 / adaptive-stop / 局数标准 | #auto-loop |
| 用户暴怒过的行为 / 沟通铁则 | #communication |
| 已修历史坑（不再复发） | #archive |
"""

def read_live():
    with open(SKILL, encoding="utf-8") as f:
        return f.read().split("\n")

def extract_pitfalls(lines, out_path):
    seg = "\n".join(lines[450:589])  # 0-indexed 450..588 = 行 451..589
    header = ("# blastgame 常见坑速查（完整表）\n\n"
              "> 2026-08-14 从 SKILL.md 外移（原 68KB）。按域分锚点；主文件「坑速查」症状索引跳到这里。\n"
              "> 结构：每个锚点 = 相关坑条目（保留原编号，编号不重排，避免与主文件/日志对不上）。\n\n"
              "## 分组说明（TODO 人工把 132 条按域归到下列锚点，或直接按域重新排序）\n"
              "## #judgment 判定分档/容差/目标偏差\n"
              "## #data-source 数据源/池子/时间防线/牌面校验\n"
              "## #probe 探针设计\n"
              "## #auto-loop 全自动流水线/时序/超时/进程\n"
              "## #leveldb 关卡数据库\n"
              "## #write-down 入库落盘/Excel/board\n"
              "## #toolchain 工具链/脚本/路径/编码\n"
              "## #communication 用户沟通/流程铁则\n"
              "## #archive 已修历史坑（✅/已修复）\n"
              "\n---\n\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + seg + "\n")
    return len((header + seg).encode("utf-8"))

def build_slim(lines, apply=False):
    drop = set()
    moved = {}
    for (s, e, kind, title, target) in SECTIONS:
        if kind in ("move", "stub", "drop"):
            drop.update(range(s, e + 1))
            moved[(s, e)] = (kind, title, target)
    kept = [l for i, l in enumerate(lines, 1) if i not in drop]

    # 插入 stubs（在合适位置：数据可靠性段替换点=原 L256 前，即 kept 中"探针设计"标题前）
    text = "\n".join(kept)

    # 顶部 2026-08-11/12 日志压缩为一行（第 20-22 行附近的段落）
    text = re.sub(r"\*\*2026-08-11/12：.*?\n", "**2026-08-11/12 日志摘要：见 references/INDEX.md 与 MEMORY.md（已压缩）。**\n",
                  text, count=1, flags=re.S)

    # 替换 References 段
    if "## References" in text:
        text = text.split("## References")[0] + SLIM_REFS_INDEX

    # 在"探针设计"标题前插入坑速查症状索引（原 L451 位置）——先放文件末尾统一处理更安全：
    # 简化：把症状索引插入到 References 段之前
    text = text.replace("## References", SYMPTOM_INDEX_TEMPLATE + "\n## References", 1)
    return text

def main():
    apply = "--apply" in sys.argv
    lines = read_live()
    total = len("\n".join(lines).encode("utf-8"))
    print(f"当前 SKILL.md: {total:,}B ({total/1024:.1f}KB)")

    draft_dir = os.path.join(os.getcwd(), "_slim_draft")
    os.makedirs(draft_dir, exist_ok=True)
    pit_path = os.path.join(draft_dir, "pitfalls.md")
    pit_size = extract_pitfalls(lines, pit_path)
    slim = build_slim(lines, apply)
    slim_size = len(slim.encode("utf-8"))
    print(f"坑表外移: {pit_size:,}B -> {pit_path}")
    print(f"新主文件: {slim_size:,}B ({slim_size/1024:.1f}KB)  [目标 ≤52KB]")

    if apply:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(SKILL, SKILL + f".bak-{ts}")
        with open(SKILL, "w", encoding="utf-8") as f:
            f.write(slim)
        with open(os.path.join(REFS, "pitfalls.md"), "w", encoding="utf-8") as f:
            f.write(open(pit_path, encoding="utf-8").read())
        print(f"--apply 已写入: {SKILL} (备份 .bak-{ts}) + references/pitfalls.md")
    else:
        out = os.path.join(draft_dir, "SKILL.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(slim)
        print(f"dry-run 草稿: {out}")
        print("> 提示：stub 摘要与坑表分组需人工提炼；确认后加 --apply 落盘。")

if __name__ == "__main__":
    main()
