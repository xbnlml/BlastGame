# -*- coding: utf-8 -*-
"""
config.py — RAG 工具配置中心
=============================
用途：统一管理语料路径、索引输出、embedding 模型、切块参数与 Top-K。
所有字段都支持环境变量覆盖（默认值即兜底），便于部署切换语料/模型而不用改代码。"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
# 语料根目录：BlastGame 游戏设计文档（MainGame 为核心，Bot/Tools 为辅助）
# 2026-08-14：语料已复制到项目内 rag/data/corpus/（一拷就走），外部路径仅作环境变量覆盖兜底。
CORPUS_ROOT = Path(os.environ.get(
    "RAG_CORPUS_ROOT",
    r"D:\download\BlastGame\hermes\rag\data\corpus",
))

# 索引输出目录（index.faiss + metadata.jsonl 都放这里）
INDEX_DIR = Path(os.environ.get(
    "RAG_INDEX_DIR",
    r"D:\download\BlastGame\hermes\rag\index",
))
INDEX_FILE = INDEX_DIR / "index.faiss"
METADATA_FILE = INDEX_DIR / "metadata.jsonl"

# 检索相关（2026-08-14 保留原值：TOP_K=5, SIMILARITY_THRESHOLD=0.3）
TOP_K = 5
SIMILARITY_THRESHOLD = 0.3

def ensure_dirs():
    """确保索引/语料目录存在（build_index 依赖）。"""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_ROOT.mkdir(parents=True, exist_ok=True)

# 只索引这些顶层子目录（MainGame 核心；Ops=skill 历史复盘，2026-08-14 扩语料）
CORPUS_SUBDIRS = [s for s in (
    os.environ.get("RAG_CORPUS_SUBDIRS", "MainGame,Ops").split(",")
) if s.strip()]

# 只处理这些后缀的文档
FILE_SUFFIXES = {".md", ".markdown"}

# ---------------------------------------------------------------------------
# Embedding 模型配置
# ---------------------------------------------------------------------------
# BGE small zh v1.5：中文小模型，512 向量维度，3072 token 上限，内存小、够快。
EMBED_MODEL_NAME = os.environ.get("RAG_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")

# BGE 系列官方推荐的 query 指令（关键！query 加前缀，passage 不加，否则检索效果差）
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# 是否对向量做 L2 归一化（cosine 相似度需要；FAISS IndexFlatIP 上的点积即 cosine）
NORMALIZE_EMBEDDINGS = True

# 是否用 GPU（TrueProphet 等；无 GPU 时请保持 False）
DEVICE = os.environ.get("RAG_DEVICE", "cpu")

# ---------------------------------------------------------------------------
# 切块参数
# ---------------------------------------------------------------------------
# 语义单元最大 token 数，超过则按段落/句子再切（不硬切）
# 经全语料消融实验选定 768（49条QA）：512=79.6%, 768=81.6%, 1024=81.6%
# 768 与 1024 效果相同但块更小更省 token，是性价比最优值
CHUNK_MAX_TOKENS = 768
# 相邻 chunk 之间保留的重叠 token 数（0 表示不重叠）
CHUNK_OVERLAP_TOKENS = 0

# ---------------------------------------------------------------------------
# 检索参数
# ---------------------------------------------------------------------------
# 向量检索 Top-K（初筛）
VECTOR_TOP_K = 20
# 混合检索最终返回条数（RRF 融合后）
FINAL_TOP_K = 10
# BM25 参数
BM25_K1 = 1.5
BM25_B = 0.75
# RRF 融合常数
RRF_K = 60
# 混合检索权重（1.0 = 完全混合，0 = 纯向量）
HYBRID_ALPHA = 0.5

# ---------------------------------------------------------------------------
# 评估配置
# ---------------------------------------------------------------------------
# golden QA 路径（评估用）
GOLDEN_QA_PATH = Path(os.environ.get(
    "RAG_GOLDEN_QA",
    r"D:\download\BlastGame\hermes\rag\data\golden_qa.json",
))
