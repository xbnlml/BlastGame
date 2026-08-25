"""Safety checks for text that is about to enter checked-in evidence or RAG."""
from __future__ import annotations

import re
from pathlib import Path


ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z])(?:[A-Za-z]:[\\/]|\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_$.-]+(?:\\[^\\\s]+)*|/(?:Users|home|tmp|etc|var|opt|root)(?:/|\b))"
)
SECRET = re.compile(
    r"(?i)(?:api[_-]?key|password|secret|authorization)\s*[:=]\s*['\"]?[^\s,'\"]{6,}"
    r"|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"
    r"|sk[-_][A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_-]{8,}|AKIA[A-Z0-9]{16}"
    r"|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\."
)


def sensitive_kind(text: str) -> str | None:
    if SECRET.search(text):
        return "credential"
    if ABSOLUTE_PATH.search(text):
        return "absolute_path"
    return None


def scan_corpus(corpus_root: Path, subdirs: list[str]) -> list[dict[str, str]]:
    """Return source/kind findings without echoing sensitive values."""
    findings: list[dict[str, str]] = []
    for subdir in subdirs:
        base = Path(corpus_root) / subdir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".markdown"}:
                continue
            relative = path.relative_to(corpus_root)
            if any(part.lower() == "archive" for part in relative.parts):
                continue
            if path.stem.lower().endswith("_archive"):
                continue
            kind = sensitive_kind(path.read_text(encoding="utf-8", errors="replace"))
            if kind:
                findings.append({"source": relative.as_posix(), "kind": kind})
    return findings
