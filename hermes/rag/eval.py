# -*- coding: utf-8 -*-
"""
eval.py — RAG 检索评估
=====================
用途：用 golden QA 测试集评估检索质量，输出 recall@k / MRR 等指标。
这是把 RAG 从"能跑"提升到"专业"的关键一步——用数据说话，不拍脑袋。"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

# 允许直接运行 / 从 rag 包导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import config  # noqa: E402
from rag.query import search  # noqa: E402

def _load_qa(path: Path) -> list[dict]:
    """加载 golden QA 集。每项：{question, expected_source, expected_keyword, note}"""
    if not path.exists():
        print(f"[eval] 未找到 QA 文件: {path}，请先创建（见 golden_qa.md 模板）")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _hit(rec, expected_source: str, expected_keyword: str) -> bool:
    """A positive hit must come from the expected current source.

    Keywords are descriptive evidence only; a generic word in an unrelated
    document must never turn a wrong source into a hit.
    """
    source = rec.get("source", "")
    parts = Path(source).parts
    if any(part.lower() == "archive" for part in parts):
        return False
    if Path(source).stem.lower().endswith("_archive"):
        return False
    if not expected_source or expected_source == "__NONE__":
        return False
    return expected_source.lower() in Path(source).stem.lower()

def evaluate(qa_path: Path, top_k_values=(1, 3, 5)) -> dict:
    qa = _load_qa(qa_path)
    if not qa:
        return {"error": "no_qa"}
    positives = [item for item in qa if item.get("expected_source") != "__NONE__"]
    negatives = [item for item in qa if item.get("expected_source") == "__NONE__"]
    print(f"[eval] 加载 {len(qa)} 条 golden QA（正例 {len(positives)} / 负例 {len(negatives)}）")

    recall = {k: 0 for k in top_k_values}
    mrr_sum = 0.0
    n = 0

    for item in positives:
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

    if not n:
        return {"error": "no_positive_qa"}

    rejected = 0
    for item in negatives:
        hits = search(item["question"], top_k=max(top_k_values), threshold=None)
        if not hits:
            rejected += 1

    print(f"\n=== 正例检索结果（{n} 条）===")
    for k in top_k_values:
        print(f"  recall@{k}: {recall[k] / n:.2%} ({recall[k]}/{n})")
    print(f"  MRR     : {mrr_sum / n:.3f}")
    rejection_rate = rejected / len(negatives) if negatives else 1.0
    print(f"  负例拒答: {rejection_rate:.2%} ({rejected}/{len(negatives)})")
    return {
        "recall": {k: recall[k] / n for k in top_k_values},
        "mrr": mrr_sum / n,
        "n": n,
        "negative": {
            "n": len(negatives),
            "rejected": rejected,
            "rejection_rate": rejection_rate,
        },
    }


def write_evaluation_report(result: dict, qa_path: Path, output_path: Path) -> Path:
    manifest = {}
    if config.MANIFEST_FILE.is_file():
        manifest = json.loads(config.MANIFEST_FILE.read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "build_id": manifest.get("build_id"),
        "qa_sha256": hashlib.sha256(qa_path.read_bytes()).hexdigest(),
        "metric_definition": {
            "positive_hit": "expected current source is required; archive and keyword-only matches do not count",
            "negative": "__NONE__ cases use the configured threshold and are reported separately",
        },
        **result,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return output_path

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="RAG 检索评估")
    ap.add_argument("--qa", type=Path, default=Path(__file__).parent / "data" / "golden_qa.json")
    ap.add_argument("--out", type=Path, default=config.EVALUATION_FILE)
    args = ap.parse_args()
    result = evaluate(args.qa)
    if "error" not in result:
        output = write_evaluation_report(result, args.qa, args.out)
        print(f"  评估报告: {output}")