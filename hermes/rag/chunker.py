# -*- coding: utf-8 -*-
"""
chunker.py — 语义切块
=====================
用途：把 markdown 文档按标题（# / ## / ###）切成"语义单元"，一条标题段落 = 一个 chunk。
超长 chunk（> max_tokens）再按段落/句子切分，绝不硬切字符。"""

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import config

# 标题行：行首 1~3 个 # + 空格 + 内容（排除 ``` 代码块内）
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
# 中英文句子结束符（用于超长切分）
_SENT_END_RE = re.compile(r"(?<=[。！？.!?])\s*|\n+")
# 中文 token 粗估：一个汉字 ≈ 1 token，英文按词。用于超长判断（够用即可）
def _estimate_tokens(text: str) -> int:
    return len(text)  # 中文为主，字符数≈token 数，足够做阈值判断

@dataclass
class Chunk:
    """一个语义单元。"""
    source: str          # 相对语料根目录的文件路径
    heading: str         # 纵贯标题路径，如 "## 1. 计分与连击规则"
    text: str            # chunk 正文
    overlap: bool = False  # 是否来自 overlap（当前实现 overlap=0，预留）
    meta: dict = field(default_factory=dict)  # 额外元数据（前后相邻标题等）

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("meta", None)
        return d

def _strip_code_blocks(text: str) -> list[str]:
    """返回非代码块的行片段。代码块内容不参与标题切分。"""
    in_code = False
    kept = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            kept.append(line)
    return kept

def split_md_by_headings(text: str) -> list[tuple[str, str]]:
    """
    按标题切分。返回 [(heading, body), ...]，heading 为标题文本（含 #），body 为该标题下的内容。
    文件开头在第一个标题之前的内容归入一个假标题 ""。
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    cur_heading = ""
    cur_body: list[str] = []
    in_code = False

    def flush():
        if cur_body:
            sections.append((cur_heading, "\n".join(cur_body).strip()))

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            cur_body.append(line)
            continue
        m = _HEADING_RE.match(line)
        if m and not in_code:
            flush()
            cur_heading = line.strip()
            cur_body = []
        else:
            cur_body.append(line)
    flush()
    # 去掉空 section
    return [(h, b) for h, b in sections if b.strip()]

def _chunk_by_sentences(text: str, max_tokens: int) -> list[str]:
    """超长 chunk：先按段落，再按句子，逐句累积到接近 max_tokens，避免硬切。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    result: list[str] = []
    buf = ""
    for para in paragraphs:
        # 段落内部按句子切
        sentences = [s.strip() for s in _SENT_END_RE.split(para) if s.strip()]
        for sent in sentences:
            if _estimate_tokens(sent) > max_tokens:
                # 单句仍超长：按字符做"软切"——按标点/空格切，最后兜底硬切（极罕见）
                if buf:
                    result.append(buf); buf = ""
                result.extend(_split_very_long(sent, max_tokens))
                continue
            if buf and _estimate_tokens(buf) + _estimate_tokens(sent) > max_tokens:
                result.append(buf); buf = ""
            buf = (buf + " " + sent).strip() if buf else sent
        # 段落间补个换行，保语义衔接
        if buf:
            buf += "\n"
    if buf.strip():
        result.append(buf.strip())
    return result

def _split_very_long(sent: str, max_tokens: int) -> list[str]:
    """极长单句兜底：按逗号/空格切，若仍超长再硬切。返回多段。"""
    parts = re.split(r"(?<=[,，;；\s])", sent)
    out, buf = [], ""
    for p in parts:
        if not p.strip():
            continue
        if _estimate_tokens(buf) + _estimate_tokens(p) > max_tokens:
            if buf:
                out.append(buf.strip()); buf = ""
            # p 本身超长则硬切
            while _estimate_tokens(p) > max_tokens:
                out.append(p[:max_tokens]); p = p[max_tokens:]
        buf += p
    if buf.strip():
        out.append(buf.strip())
    return out or [sent]

def chunk_markdown_file(path: Path, rel_source: str) -> list[Chunk]:
    """读取单个 md 文件并切块。rel_source 为相对语料根目录的路径（用于溯源）。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    chunks: list[Chunk] = []
    for heading, body in split_md_by_headings(text):
        if _estimate_tokens(body) <= config.CHUNK_MAX_TOKENS:
            chunks.append(Chunk(source=rel_source, heading=heading, text=body))
        else:
            # 超长：按段落/句子细分
            for part in _chunk_by_sentences(body, config.CHUNK_MAX_TOKENS):
                chunks.append(Chunk(source=rel_source, heading=heading, text=part))
    return chunks

def chunk_corpus(corpus_root: Path, subdirs: list[str]) -> list[Chunk]:
    """遍历语料目录，返回所有文件的 chunk。"""
    all_chunks: list[Chunk] = []
    for sub in subdirs:
        base = corpus_root / sub
        if not base.exists():
            print(f"[chunker] 跳过不存在目录: {base}")
            continue
        for f in sorted(base.rglob("*")):
            if f.suffix.lower() not in config.FILE_SUFFIXES:
                continue
            relative_parts = f.relative_to(corpus_root).parts
            if any(part.lower() == "archive" for part in relative_parts):
                continue
            if f.stem.lower().endswith("_archive"):
                continue
            rel = f.relative_to(corpus_root).as_posix()
            try:
                chunks = chunk_markdown_file(f, rel)
                if rel.startswith("Ops/"):
                    prefix = (
                        "[历史复盘] 本片段记录当时状态，可能已被后续实现替代；"
                        "当前判定以 project-state/rules.json 和现行代码为准。\n"
                    )
                    for chunk in chunks:
                        chunk.text = prefix + chunk.text
                all_chunks.extend(chunks)
            except Exception as e:  # 单个文件失败不拖垮整体
                print(f"[chunker] 跳过 {f}: {e}")
    return all_chunks

if __name__ == "__main__":
    # 命令行自测：python -m rag.chunker
    import sys
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        rel = p.relative_to(config.CORPUS_ROOT).as_posix() if p.is_absolute() else p.name
        for c in chunk_markdown_file(p, rel):
            print(f"[{c.heading}] ({len(c.text)}字) {c.text[:60]}...")
    else:
        print(f"[chunker] 遍历 {config.CORPUS_ROOT} 子目录 {config.CORPUS_SUBDIRS}")
        cs = chunk_corpus(config.CORPUS_ROOT, config.CORPUS_SUBDIRS)
        print(f"[chunker] 共 {len(cs)} 个 chunk")