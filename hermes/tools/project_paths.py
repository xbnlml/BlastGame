"""Resolve the external BlastGame Unity workspace without machine-specific paths."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def _looks_like_unity_project(path: Path) -> bool:
    return (
        (path / "Assets").is_dir()
        and (path / "ProjectSettings" / "ProjectVersion.txt").is_file()
    )


def resolve_unity_repo(
    hermes_dir: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the Unity workspace path.

    Resolution order: explicit ``BLASTGAME_REPO``; a Unity project containing
    the checked-out ``hermes`` directory; the current user's Documents folder.
    If no live workspace exists, return the checkout root so read-only/help
    commands still have a deterministic path and live commands fail on missing
    prerequisites rather than another user's machine path.
    """
    env = os.environ if environ is None else environ
    explicit = env.get("BLASTGAME_REPO")
    if explicit:
        return Path(explicit).expanduser().resolve()

    hermes = Path(hermes_dir or Path(__file__).resolve().parents[1]).resolve()
    checkout = hermes.parent
    documents = Path(home or Path.home()).expanduser().resolve() / "Documents" / "BlastGame"
    for candidate in (checkout, documents):
        if _looks_like_unity_project(candidate):
            return candidate.resolve()
    return checkout
