# -*- coding: utf-8 -*-
"""
fusion.py — 混合检索融合（RRF）
==============================
用途：把向量检索结果 + BM25 关键词结果，用 RRF（Reciprocal Rank Fusion）合并成一份。"""

import json
from pathlib import Path

from . import config
from .query import Hit, _load_metadata

RRF_K = 60  # RRF 常数（业界默认）

def rrf_fuse(vector_hits: list[Hit], bm25_hits: list[tuple[int, float]], meta: list[dict]) -> list[Hit]:
    """
    融合向量命中 + BM25 命中。
    vector_hits: 向量检索返回的 Hit 列表（已带 source/heading/text）
    bm25_hits: BM25 返回的 [(doc_index, score)]，doc_index 对应当前 metadata 行
    meta: metadata 记录列表（行号=FAISS index）
    返回按 RRF 分降序的 Hit 列表。
    """
    # 向量结果的排名：通过 source+heading 反查 metadata 行号
    source_heading_to_idx = {}
    for i, rec in enumerate(meta):
        key = (rec.get("source", ""), rec.get("heading", ""))
        source_heading_to_idx.setdefault(key, i)

    vec_rrf: dict[int, float] = {}
    for rank, h in enumerate(vector_hits, 1):
        idx = source_heading_to_idx.get((h.source, h.heading))
        if idx is None:
            continue
        vec_rrf[idx] = vec_rrf.get(idx, 0.0) + 1.0 / (RRF_K + rank)

    bm25_rrf: dict[int, float] = {}
    for rank, (doc_idx, _score) in enumerate(bm25_hits, 1):
        bm25_rrf[doc_idx] = bm25_rrf.get(doc_idx, 0.0) + 1.0 / (RRF_K + rank)

    # 合并分数
    fused: dict[int, float] = {}
    for idx, s in vec_rrf.items():
        fused[idx] = fused.get(idx, 0.0) + s
    for idx, s in bm25_rrf.items():
        fused[idx] = fused.get(idx, 0.0) + s

    # 排序并组装 Hit
    ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    hits: list[Hit] = []
    for idx, rrf_score in ordered:
        rec = meta[idx]
        hits.append(Hit(score=rrf_score, source=rec.get("source", ""),
                        heading=rec.get("heading", ""), text=rec.get("text", "")))
    return hits

def load_meta_for_fusion() -> list[dict]:
    return _load_metadata()

if __name__ == "__main__":
    print("[fusion] RRF 融合模块就绪")