# -*- coding: utf-8 -*-
"""
eval.py — RAG 检索评估
=====================
用途：用 golden QA 测试集评估检索质量，输出 recall@k / MRR 等指标。
这是把 RAG 从"能跑"提升到"专业"的关键一步——用数据说话，不拍脑袋。"""

import argparse
import json
import sys
from pathlib import Path

# 允许直接运行 / 从 rag 包导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag.query import search  # noqa: E402

def _load_qa(path: Path) -> list[dict]:
    """加载 golden QA 集。每项：{question, expected_source, expected_keyword, note}"""
    if not path.exists():
        print(f"[eval] 未找到 QA 文件: {path}，请先创建（见 golden_qa.md 模板）")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _hit(rec, expected_source: str, expected_keyword: str) -> bool:
    """判断一条检索命中是否有效：来源匹配 或 正文含关键词。"""
    source = rec.get("source", "")
    text = rec.get("text", "")
    if expected_source and expected_source.lower() in source.lower():
        return True
    if expected_keyword and expected_keyword in text:
        return True
    return False

def evaluate(qa_path: Path, top_k_values=(1, 3, 5)) -> dict:
    qa = _load_qa(qa_path)
    if not qa:
        return {"error": "no_qa"}
    print(f"[eval] 加载 {len(qa)} 条 golden QA")

    recall = {k: 0 for k in top_k_values}
    mrr_sum = 0.0
    n = 0

    for item in qa:
        q = item["question"]
        exp_src = item.get("expected_source", "")
        exp_kw = item.get("expected_keyword", "")
        hits = search(q, top_k=max(top_k_values),
                      threshold=0.0)  # 评估时不设阈值，看召回
        # 命中判定
        hit_flags = [_hit(h.__dict__, exp_src, exp_kw) for h in hits]
        # recall@k
        for k in top_k_values:
            if any(hit_flags[:k]):
                recall[k] += 1
        # MRR：第一个命中位置
        for i, hf in enumerate(hit_flags):
            if hf:
                mrr_sum += 1.0 / (i + 1)
                break
        n += 1

    print(f"\n=== 评估结果（{n} 条 QA）===")
    for k in top_k_values:
        print(f"  recall@{k}: {recall[k] / n:.2%} ({recall[k]}/{n})")
    print(f"  MRR     : {mrr_sum / n:.3f}")
    return {"recall": {k: recall[k] / n for k in top_k_values},
            "mrr": mrr_sum / n, "n": n}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="RAG 检索评估")
    ap.add_argument("--qa", type=Path, default=Path(__file__).parent / "data" / "golden_qa.json")
    args = ap.parse_args()
    evaluate(args.qa)