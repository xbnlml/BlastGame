# -*- coding: utf-8 -*-
"""
build_index.py — 建索引
=======================
用途：遍历语料 → 切块 → 转向量 → 写 FAISS 索引(index.faiss) + 元数据 sidecar(metadata.jsonl)。"""

import hashlib
import importlib.metadata
import json
import os
import platform
import time
from pathlib import Path

import faiss
import numpy as np

from . import config
from .chunker import chunk_corpus
from .embedder import encode_passages, get_dim
from .safety import scan_corpus

def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _corpus_manifest(corpus_root: Path, subdirs: list[str]) -> tuple[list[dict], str]:
    files = []
    for subdir in subdirs:
        base = corpus_root / subdir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in config.FILE_SUFFIXES:
                continue
            relative = path.relative_to(corpus_root)
            if any(part.lower() == "archive" for part in relative.parts):
                continue
            if path.stem.lower().endswith("_archive"):
                continue
            files.append({"source": relative.as_posix(), "sha256": _sha256_file(path)})
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return files, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dependency_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": importlib.metadata.version("numpy"),
        "faiss-cpu": importlib.metadata.version("faiss-cpu"),
        "sentence-transformers": importlib.metadata.version("sentence-transformers"),
    }

def build_index(corpus_root=config.CORPUS_ROOT,
                subdirs=config.CORPUS_SUBDIRS,
                index_dir=config.INDEX_DIR) -> tuple[Path, Path]:
    """建索引，返回 (index 路径, metadata 路径)。"""
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "index.faiss"
    metadata_file = index_dir / "metadata.jsonl"
    manifest_file = index_dir / "build_manifest.json"
    index_tmp = index_dir / "index.faiss.tmp"
    metadata_tmp = index_dir / "metadata.jsonl.tmp"
    manifest_tmp = index_dir / "build_manifest.json.tmp"
    findings = scan_corpus(Path(corpus_root), list(subdirs))
    if findings:
        summary = ", ".join(f"{item['source']} ({item['kind']})" for item in findings)
        raise RuntimeError(f"语料安全检查失败: {summary}")
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

    corpus_files, corpus_sha256 = _corpus_manifest(Path(corpus_root), list(subdirs))
    build_spec = {
        "model": {"name": config.EMBED_MODEL_NAME, "revision": config.EMBED_MODEL_REVISION},
        "chunking": {
            "max_tokens": config.CHUNK_MAX_TOKENS,
            "overlap_tokens": config.CHUNK_OVERLAP_TOKENS,
            "subdirs": list(subdirs),
        },
        "corpus_sha256": corpus_sha256,
    }
    build_id = hashlib.sha256(
        json.dumps(build_spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    # ---- 写临时产物；全部成功后原子替换 ----
    index = faiss.IndexFlatIP(dim)  # 内积；向量已 L2 归一化 → 等价 cosine
    index.add(vecs)                 # 必须是 float32
    faiss.write_index(index, str(index_tmp))

    # ---- 写元数据 sidecar（与索引顺序一一对应）----
    n = 0
    with open(metadata_tmp, "w", encoding="utf-8") as f:
        for c in chunks:
            rec = {
                "index": n,
                "source": c.source,
                "heading": c.heading,
                "text": c.text,
                "chars": len(c.text),
                "hash": _hash_text(c.text),
                "build_id": build_id,
                "built_at": ts,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    manifest = {
        "schema_version": 1,
        "build_id": build_id,
        "built_at": ts,
        **build_spec,
        "dependencies": _dependency_versions(),
        "dimension": dim,
        "chunk_count": n,
        "corpus_files": corpus_files,
        "index_sha256": _sha256_file(index_tmp),
        "metadata_sha256": _sha256_file(metadata_tmp),
    }
    with open(manifest_tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    os.replace(index_tmp, index_file)
    os.replace(metadata_tmp, metadata_file)
    os.replace(manifest_tmp, manifest_file)
    print(f"[build] FAISS 索引已写入: {index_file} ({index.ntotal} 条)")
    print(f"[build] 元数据已写入: {metadata_file} ({n} 行)")
    print(f"[build] 构建清单已写入: {manifest_file} (build_id={build_id})")

    # 加载自检：确认能读回
    back = faiss.read_index(str(index_file))
    assert back.ntotal == n, "索引条目数与元数据行数不一致"
    print(f"[build] 自检通过：索引 {back.ntotal} 条 == 元数据 {n} 行")
    return index_file, metadata_file

if __name__ == "__main__":
    # 命令行：python -m rag.build_index
    build_index()