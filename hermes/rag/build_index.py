# -*- coding: utf-8 -*-
"""
build_index.py — 建索引
=======================
用途：遍历语料 → 切块 → 转向量 → 写 FAISS 索引(index.faiss) + 元数据 sidecar(metadata.jsonl)。"""

import hashlib
import json
import time
from pathlib import Path

import faiss
import numpy as np

from . import config
from .chunker import chunk_corpus
from .embedder import encode_passages, get_dim

def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def build_index(corpus_root=config.CORPUS_ROOT,
                subdirs=config.CORPUS_SUBDIRS,
                index_dir=config.INDEX_DIR) -> tuple[Path, Path]:
    """建索引，返回 (index 路径, metadata 路径)。"""
    config.ensure_dirs()
    print(f"[build] 切块语料: {corpus_root} 子目录 {subdirs}")
    chunks = chunk_corpus(corpus_root, subdirs)
    if not chunks:
        raise RuntimeError("没有切到任何 chunk，请检查语料路径")
    print(f"[build] 共 {len(chunks)} 个 chunk")

    texts = [c.text for c in chunks]
    print(f"[build] 向量化 {len(texts)} 段 ...")
    vecs = encode_passages(texts)
    dim = get_dim()
    assert vecs.shape[1] == dim, f"向量维度 {vecs.shape[1]} != 模型维度 {dim}"
    print(f"[build] 向量维度 {dim}, 形状 {vecs.shape}")

    # ---- 写 FAISS 索引 ----
    index = faiss.IndexFlatIP(dim)  # 内积；向量已 L2 归一化 → 等价 cosine
    index.add(vecs)                 # 必须是 float32
    faiss.write_index(index, str(config.INDEX_FILE))
    print(f"[build] FAISS 索引已写入: {config.INDEX_FILE} ({index.ntotal} 条)")

    # ---- 写元数据 sidecar（与索引顺序一一对应）----
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    with open(config.METADATA_FILE, "w", encoding="utf-8") as f:
        for c in chunks:
            rec = {
                "index": n,
                "source": c.source,
                "heading": c.heading,
                "text": c.text,
                "chars": len(c.text),
                "hash": _hash_text(c.text),
                "built_at": ts,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"[build] 元数据已写入: {config.METADATA_FILE} ({n} 行)")

    # 加载自检：确认能读回
    back = faiss.read_index(str(config.INDEX_FILE))
    assert back.ntotal == n, "索引条目数与元数据行数不一致"
    print(f"[build] 自检通过：索引 {back.ntotal} 条 == 元数据 {n} 行")
    return config.INDEX_FILE, config.METADATA_FILE

if __name__ == "__main__":
    # 命令行：python -m rag.build_index
    build_index()