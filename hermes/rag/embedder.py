# -*- coding: utf-8 -*-
"""
embedder.py — 文本转向量
========================
用途：封装 SentenceTransformer(bge-small-zh-v1.5)，提供：
  - encode_queries(texts)：query 加 BGE 指令 + L2 归一化
  - encode_passages(texts)：passage 不加指令 + L2 归一化"""

import numpy as np
from sentence_transformers import SentenceTransformer

from . import config

_model = None  # 单例缓存

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"[embedder] 加载模型 {config.EMBED_MODEL_NAME} ...")
        _model = SentenceTransformer(config.EMBED_MODEL_NAME, device=config.DEVICE)
    return _model

def _normalize(vec: np.ndarray) -> np.ndarray:
    """L2 归一化（行方向）。"""
    norms = np.linalg.norm(vec, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 防除零
    return vec / norms

def encode_queries(texts: list[str]) -> np.ndarray:
    """query 编码：加 BGE 指令 + 归一化。返回 (N, dim) float32 数组。"""
    model = _get_model()
    prefixed = [config.QUERY_INSTRUCTION + t for t in texts]
    vec = model.encode(prefixed, normalize_embeddings=config.NORMALIZE_EMBEDDINGS,
                       convert_to_numpy=True)
    if config.NORMALIZE_EMBEDDINGS:
        vec = _normalize(vec)
    return vec.astype("float32")

def encode_passages(texts: list[str]) -> np.ndarray:
    """passage 编码：不加指令 + 归一化。"""
    model = _get_model()
    vec = model.encode(texts, normalize_embeddings=config.NORMALIZE_EMBEDDINGS,
                       convert_to_numpy=True)
    if config.NORMALIZE_EMBEDDINGS:
        vec = _normalize(vec)
    return vec.astype("float32")

def get_dim() -> int:
    """返回向量维度（bge-small-zh-v1.5 = 512）。"""
    return _get_model().get_sentence_embedding_dimension()

if __name__ == "__main__":
    # 自测：python -m rag.embedder
    q = encode_queries(["游戏计分逻辑是怎样的"])
    p = encode_passages(["计分与连击规则", "结算顺序"])
    print("query dim:", q.shape)
    print("passage dim:", p.shape)
    sim = q @ p.T
    print("query vs 各 passage 相似度:", sim.tolist())
    print("query 归一化 L2 范数:", float(np.linalg.norm(q[0])))
    print("passage 归一化 L2 范数:", float(np.linalg.norm(p[0])))