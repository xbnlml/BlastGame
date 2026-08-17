# -*- coding: utf-8 -*-
"""
bm25.py — 关键词检索（BM25）
============================
用途：对同一语料做关键词精确检索，与向量检索互补，最后用 RRF 融合。"""

import math
import re
from collections import Counter
from pathlib import Path

from . import config

# 中文 bi-gram 分词（不依赖 jieba）：对短文本召回够用
def tokenize(text: str) -> list[str]:
    text = text.lower()
    # 驼峰/下划线切分：BlastReplayActionRecord -> blast replay action record
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"[_\-/]", " ", text)
    # 提取中英文词 + 中文 bi-gram
    latin = re.findall(r"[a-z][a-z0-9]{1,}", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    # 中文连续字 -> 双字 bi-gram（如 "计分规则" -> 计分/分规/规则），提升子串召回
    cjk_run = re.sub(r"[^一-鿿]", " ", text).split()
    bigrams = []
    for run in cjk_run:
        if len(run) == 1:
            bigrams.append(run)
        for i in range(len(run) - 1):
            bigrams.append(run[i:i + 2])
    return latin + bigrams

class BM25Index:
    """一次性内存 BM25 索引（中小语料够用，不需持久化）。"""

    def __init__(self, docs: list[dict]):
        """
        docs: [{"index": int, "text": str}, ...]
        text 为 chunk 原文（用于召回匹配）。
        """
        self.doc_texts = [d["text"] for d in docs]
        self.doc_tokens = [tokenize(self.doc_texts[i]) for i in range(len(docs))]
        self.N = len(docs)
        self.avgdl = sum(len(t) for t in self.doc_tokens) / max(1, self.N)
        self.idf: dict[str, float] = {}
        self._build_idf()

    def _build_idf(self):
        df: Counter = Counter()
        for toks in self.doc_tokens:
            seen = set(toks)
            for t in seen:
                df[t] += 1
        for t, n in df.items():
            self.idf[t] = math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """返回 [(doc_index, score), ...] 按分降序。"""
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        # 每个文档算 BM25 分数
        scores: list[tuple[int, float]] = []
        for i in range(self.N):
            tf = Counter(self.doc_tokens[i])
            dl = len(self.doc_tokens[i])
            score = 0.0
            for t in set(q_tokens):
                if t in self.idf and tf[t] > 0:
                    k1, b = 1.5, 0.75
                    tf_part = tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / max(1, self.avgdl)))
                    score += self.idf[t] * tf_part
            if score > 0:
                scores.append((i, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

def build_bm25_from_metadata(metadata_path: Path):
    """从 metadata.jsonl 构建 BM25 索引。"""
    docs = []
    with open(metadata_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            import json
            rec = json.loads(line)
            docs.append({"index": rec.get("index", len(docs)), "text": rec.get("text", "")})
    return BM25Index(docs)

if __name__ == "__main__":
    # 自测：python -m rag.bm25
    idx = BM25Index([
        {"index": 0, "text": "游戏计分纯逻辑在 Core/BlastScorePureLogic.cs"},
        {"index": 1, "text": "回放动作记录 BlastReplayActionRecord 字段"},
        {"index": 2, "text": "金币经济系统在 Coin_Economy_Logic"},
    ])
    for q in ["BlastScorePureLogic", "回放记录", "金币"]:
        print(f"query={q!r} -> {idx.search(q, top_k=3)}")