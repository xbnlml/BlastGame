# -*- coding: utf-8 -*-
"""
rag 包 — 本地 RAG 工具（BlastGame 文档语义检索）
==============================================
模块：
  config.py       配置中心（路径/模型/切块/TopK，环境变量可覆盖）
  chunker.py      语义切块（按标题切，超长按段落/句子）
  embedder.py     向量化（BGE 指令 + L2 归一化）
  build_index.py  建索引（FAISS + 元数据 sidecar）
  query.py        检索问答（带来源）
"""

from . import config, chunker, embedder, build_index, query

__all__ = ["config", "chunker", "embedder", "build_index", "query"]
__version__ = "0.1.0"