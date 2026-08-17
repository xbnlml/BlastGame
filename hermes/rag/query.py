# -*- coding: utf-8 -*-
"""
query.py — 检索问答
===================
用途：给定问题 → query 编码（带 BGE 指令 + L2 归一化）→ FAISS 检索 Top-K →
返回带来源(source/heading)的相关片段，按相似度降序输出。"""

import argparse
import json
from dataclasses import dataclass, field

import faiss
import numpy as np

from . import config
from .embedder import encode_queries

@dataclass
class Hit:
    """一条检索结果。"""
    score: float
    source: str
    heading: str
    text: str

    def __str__(self) -> str:
        return (f"[score={self.score:.3f}] {self.source} :: {self.heading}\n"
                f"    {self.text}")

def _load_metadata() -> list[dict]:
    """读取 metadata.jsonl，返回记录列表（行号 = FAISS index）。"""
    recs: list[dict] = []
    with open(config.METADATA_FILE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rec["_row"] = i
            recs.append(rec)
    return recs

def search(question: str, top_k: int = None,
           threshold: float = None) -> list[Hit]:
    """检索主流程。返回按相似度降序的 Hit 列表。"""
    top_k = top_k or config.TOP_K
    threshold = config.SIMILARITY_THRESHOLD if threshold is None else threshold

    # 1) query 编码（带 BGE 指令 + 归一化）
    qvec = encode_queries([question])[0]

    # 2) 加载索引与元数据
    index = faiss.read_index(str(config.INDEX_FILE))
    recs = _load_metadata()
    assert index.ntotal == len(recs), "索引与元数据不一致，请重新 build_index"

    # 3) FAISS 检索（IndexFlatIP + 归一化 → distances 即 cosine）
    distances, indices = index.search(np.expand_dims(qvec, 0), k=min(top_k, index.ntotal))

    # 4) 组装结果
    hits: list[Hit] = []
    seen_sources: list[str] = []
    for score, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        if score < threshold:
            continue
        rec = recs[idx]
        hit = Hit(score=float(score), source=rec["source"],
                  heading=rec["heading"], text=rec["text"])
        hits.append(hit)
        if rec["source"] not in seen_sources:
            seen_sources.append(rec["source"])
    return hits

def search_hybrid(question: str, top_k: int = None,
                  threshold: float = None) -> list[Hit]:
    """
    混合检索：向量检索 + BM25 关键词，用 RRF 融合。
    解决纯向量对精确专有名词（类名/方法名/字段名）不敏感的问题。
    """
    from .bm25 import build_bm25_from_metadata
    from .fusion import rrf_fuse, load_meta_for_fusion

    top_k = top_k or config.TOP_K

    # 1) 向量检索（现有逻辑）
    vec_hits = search(question, top_k=max(top_k, 10), threshold=threshold)

    # 2) BM25 关键词检索
    meta = load_meta_for_fusion()
    bm25 = build_bm25_from_metadata(config.METADATA_FILE)
    bm25_hits = bm25.search(question, top_k=max(top_k, 10))

    # 3) RRF 融合
    fused = rrf_fuse(vec_hits, bm25_hits, meta)
    return fused[:top_k]

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="本地 RAG 检索")
    ap.add_argument("question", nargs="?", help="问题；缺省则进入交互模式")
    ap.add_argument("-k", "--top-k", type=int, default=None, help=f"返回条数(默认 {config.TOP_K})")
    ap.add_argument("-t", "--threshold", type=float, default=None, help="相似度阈值")
    ap.add_argument("--hybrid", action="store_true", help="使用混合检索(向量+BM25+RRF)")
    args = ap.parse_args(argv)

    if args.question:
        _run(args.question, args.top_k, args.threshold, hybrid=args.hybrid)
    else:
        print("进入交互模式，输入问题回车检索，'q' 退出。")
        while True:
            try:
                q = input("问题> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q or q.lower() in ("q", "quit", "exit"):
                break
            _run(q, args.top_k, args.threshold, hybrid=args.hybrid)

def _run(question: str, top_k: int | None, threshold: float | None, hybrid: bool = False) -> None:
    print(f"\n=== 问题：{question} ===（{'混合检索' if hybrid else '向量检索'}）")
    if hybrid:
        hits = search_hybrid(question, top_k=top_k, threshold=threshold)
    else:
        hits = search(question, top_k=top_k, threshold=threshold)
    if not hits:
        print("未检索到相关片段。")
        return
    for i, h in enumerate(hits, 1):
        print(f"{i}. {h}")
    # 汇总命中来源
    srcs = sorted({h.source for h in hits})
    print(f"\n命中来源: {', '.join(srcs)}")

if __name__ == "__main__":
    main()