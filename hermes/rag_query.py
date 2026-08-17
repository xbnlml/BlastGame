#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rag_query.py — BlastGame 游戏文档 RAG 检索命令行工具
====================================================
用法（agent 或用户在终端调用）：
    python rag_query.py "游戏计分逻辑是怎样的"
    python rag_query.py "金币经济系统怎么运作" -k 3
    python rag_query.py "回放系统" -k 2 --full

说明：对 BlastGame/Doc 下的游戏模块文档做语义检索，返回最相关的片段（带来源）。
这是独立命令行入口，不依赖 `python -m rag`，可直接运行。"""

import argparse
import sys

# 允许直接运行（不依赖 -m rag）
sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])

from rag.query import search  # noqa: E402

def main() -> None:
    ap = argparse.ArgumentParser(description="BlastGame 游戏文档语义检索")
    ap.add_argument("question", help="要检索的问题")
    ap.add_argument("-k", "--top-k", type=int, default=3, help="返回条数(默认3)")
    ap.add_argument("-t", "--threshold", type=float, default=None, help="相似度阈值")
    ap.add_argument("--full", action="store_true", help="显示完整片段(默认截断)")
    ap.add_argument("--hybrid", action="store_true", help="使用混合检索(向量+BM25+RRF)")
    args = ap.parse_args()

    if args.hybrid:
        from rag.query import search_hybrid
        hits = search_hybrid(args.question, top_k=args.top_k, threshold=args.threshold)
    else:
        hits = search(args.question, top_k=args.top_k, threshold=args.threshold)
    if not hits:
        print("未检索到相关片段。")
        return

    print(f"问题：{args.question}")
    print(f"命中 {len(hits)} 条：\n")
    for i, h in enumerate(hits, 1):
        text = h.text if args.full else (h.text[:120] + ("..." if len(h.text) > 120 else ""))
        print(f"{i}. [score={h.score:.3f}] {h.source} :: {h.heading}")
        print(f"   {text}\n")

if __name__ == "__main__":
    main()