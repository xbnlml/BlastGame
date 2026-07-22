"""
token_saver.py — Hermes 多档位数值工作的紧凑输出工具

用法：在 execute_code 里直接 import
    from token_saver import tsv_batch, rule_check, tsv

原理：不压缩输入，而是让输出只包含你要看的信息。
"""

import pandas as pd
from io import StringIO


def tsv(csv_path: str) -> str:
    """
    读 CSV 并输出紧凑行格式（一行一关，只含关键列）
    比 pd.read_csv().to_string() 省 ~70% token
    """
    df = pd.read_csv(csv_path)
    cols = [c for c in ["level", "DifficultyLevel", "winkate", "winCount", "failCount"]
            if c in df.columns]
    lines = [" | ".join(cols)]
    for _, row in df.iterrows():
        vals = [str(row[c]) for c in cols]
        lines.append(" | ".join(vals))
    return "\n".join(lines)


def tsv_batch(csv_t3: str = None, csv_t4: str = None, csv_t5: str = None,
              csv_t1: str = None, csv_t2: str = None) -> str:
    """
    合并多档 CSV，输出一关一行的档位胜率表。
    自动匹配关卡号对齐各档数据。行列数 ≈ (关卡数+1) × 7。
    """
    tiers = {}
    for label, path in [("T1", csv_t1), ("T2", csv_t2), ("T3", csv_t3),
                         ("T4", csv_t4), ("T5", csv_t5)]:
        if path:
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                lv = int(row["level"])
                if lv not in tiers:
                    tiers[lv] = {"level": lv, "diff": int(row["DifficultyLevel"])}
                tiers[lv][label] = round(row["winkate"] * 100, 1)

    if not tiers:
        return ""

    diff_name = {0: "N", 1: "H", 2: "SH"}
    header = "level | diff | T1 | T2 | T3 | T4 | T5"
    rows = [header]
    for lv in sorted(tiers):
        d = tiers[lv]
        dn = diff_name.get(d.get("diff", 0), "?")
        t1 = f'{d.get("T1", "-"):>5}'
        t2 = f'{d.get("T2", "-"):>5}'
        t3 = f'{d.get("T3", "-"):>5}'
        t4 = f'{d.get("T4", "-"):>5}'
        t5 = f'{d.get("T5", "-"):>5}'
        rows.append(f"{lv:5d} |  {dn}  | {t1} | {t2} | {t3} | {t4} | {t5}")
    return "\n".join(rows)


def rule_check(t1: float, t3: float, t5: float, diff: int) -> dict:
    """
    快速规则判定（RULES.md §4-§6）
    返回 { pass: bool, reasons: [str] }
    diff: 0=Normal, 1=Hard, 2=SuperHard
    """
    result = {"pass": True, "reasons": []}

    # T3 锚点
    if diff == 0:  # Normal ≥60%
        if t3 < 60:
            result["pass"] = False
            result["reasons"].append(f"R-H3: Normal T3={t3:.1f}% <60%")
    elif diff == 1:  # Hard 30-60%
        if t3 < 30 or t3 > 60:
            result["pass"] = False
            result["reasons"].append(f"R-H3: Hard T3={t3:.1f}% not in [30,60]")
    else:  # SuperHard ≤50%
        if t3 > 50:
            result["pass"] = False
            result["reasons"].append(f"R-H3: SH T3={t3:.1f}% >50%")

    # 高档差 T1-T3 ≥15%（入库放宽）
    d13 = t1 - t3
    if d13 < 15:
        if d13 < 5:
            result["pass"] = False
            result["reasons"].append(f"R-H2: T1-T3={d13:.1f}% <5%")
        elif d13 < 7:
            result["reasons"].append(f"R-S2: T1-T3={d13:.1f}% <7%")
        else:
            result["reasons"].append(f"R-S1: T1-T3={d13:.1f}% <15%")

    # 中低档差 T3-T5 ≥7%（入库放宽）；<5% 一律硬性违规
    d35 = t3 - t5
    if d35 < 7:
        if d35 < 5:
            result["pass"] = False
            result["reasons"].append(f"R-H2: T3-T5={d35:.1f}% <5%")
        else:
            result["reasons"].append(f"R-S2: T3-T5={d35:.1f}% <7%")

    return result
