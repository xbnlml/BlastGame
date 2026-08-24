#!/usr/bin/env python3
"""Legacy Unity batch discovery and post-run acceptance checks.

This keeps the active workflow simple without trusting a newest-directory
heuristic: submit_batch_unity must expose the explicit legacy batch directory,
and Unity must have copied the loaded asset snapshots into it.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.asset_patcher import find_ddc_block


class LegacyBatchVerificationError(RuntimeError):
    """The legacy batch cannot safely enter the analysis pool."""


def _norm_config(config: Mapping[str, Any]) -> tuple[str, str, str, float]:
    if not isinstance(config, Mapping):
        raise LegacyBatchVerificationError(
            f"expected config mapping, got {type(config).__name__}"
        )
    ratios = ",".join(str(config.get("ratios", "")).replace("，", ",").split())
    ratios = ratios.replace(" ", "")
    return (
        str(config.get("sd", "")).strip(),
        str(config.get("sc", "")).strip(),
        ratios,
        round(float(config.get("of", 0) or 0), 6),
    )


def read_ddc_snapshot(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read DDC four-tuples from a copied Unity asset file."""
    asset_path = Path(path)
    try:
        lines = asset_path.read_text(encoding="utf-8").splitlines(True)
    except OSError as exc:
        raise LegacyBatchVerificationError(f"asset snapshot unreadable: {asset_path}: {exc}") from exc

    start, end = find_ddc_block(lines)
    if start is None or end is None:
        raise LegacyBatchVerificationError(f"asset snapshot DDC block missing: {asset_path}")

    configs: list[dict[str, Any]] = []
    index = start + 1
    while index < end:
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if not line.startswith("- "):
            index += 1
            continue
        config: dict[str, Any] = {}
        first = line[2:].strip()
        if ":" in first:
            key, value = first.split(":", 1)
            key, value = key.strip(), value.strip().strip('"')
            if key == "StartDifficulty":
                config["sd"] = int(value)
        index += 1
        while index < end:
            nested = lines[index].strip()
            if not nested or nested.startswith("- "):
                break
            if ":" in nested:
                key, value = nested.split(":", 1)
                key, value = key.strip(), value.strip().strip('"')
                if key == "StartDifficulty":
                    config["sd"] = int(value)
                elif key == "ShuffleSplitCount":
                    config["sc"] = int(value)
                elif key == "ShuffleSplitRatios":
                    config["ratios"] = value
                elif key == "ShuffleOverflowFactor":
                    config["of"] = float(value)
            index += 1
        if config:
            configs.append(config)
    return configs


def _parse_tier(value: Any) -> int | None:
    match = re.search(r"(?:T)?([1-5])", str(value or ""))
    return int(match.group(1)) if match else None


def _parse_float(row: Mapping[str, Any], *names: str) -> float:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            parsed = float(value)
            if 0 <= parsed <= 1:
                return parsed
    raise LegacyBatchVerificationError(f"summary row missing win rate: {dict(row)}")


def _summary_records(batch_dir: Path) -> dict[tuple[str, int], dict[str, Any]]:
    records: dict[tuple[str, int], dict[str, Any]] = {}
    files = sorted(batch_dir.rglob("campaign-summary*.csv"))
    if not files:
        raise LegacyBatchVerificationError(f"campaign-summary CSV missing under {batch_dir}")

    for csv_path in files:
        try:
            handle = csv_path.open("r", encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise LegacyBatchVerificationError(f"summary unreadable: {csv_path}: {exc}") from exc
        with handle:
            for row in csv.DictReader(handle):
                level = str(row.get("level", "")).strip()
                tier = _parse_tier(row.get("Tier"))
                if not level or tier is None:
                    continue
                win_count = int(row.get("winCount", 0) or 0)
                fail_count = int(row.get("failCount", 0) or 0)
                total = win_count + fail_count
                if total <= 0:
                    raise LegacyBatchVerificationError(
                        f"summary has no games: {csv_path} L{level} T{tier}"
                    )
                record = {
                    "level": level,
                    "tier": tier,
                    "wr": round(_parse_float(row, "winkate", "win_rate", "wr") * 100, 4),
                    "totalGames": total,
                    "winGames": win_count,
                    "failGames": fail_count,
                    "sd": str(row.get("startDifficulty", "")).strip(),
                    "sc": str(row.get("shuffleSplitCount", "")).strip(),
                    "ratios": str(row.get("shuffleSplitRatios", "")).strip(),
                    "of": str(row.get("shuffleOverflowFactor", "")).strip(),
                    "boardFingerprint": str(row.get("BoardFingerprint", "")).strip(),
                    "source": "bot",
                    "source_path": str(csv_path),
                }
                key = (level, tier)
                previous = records.get(key)
                if previous is not None:
                    if (
                        _norm_config(previous) != _norm_config(record)
                        or abs(float(previous["wr"]) - float(record["wr"])) > 1e-6
                    ):
                        raise LegacyBatchVerificationError(
                            f"duplicate conflicting summary: L{level} T{tier}"
                        )
                    continue
                records[key] = record
    return records


def _snapshot_path(batch_dir: Path, level: str) -> Path:
    candidates = [
        batch_dir / "level-assets" / "test" / f"{level}.asset",
        batch_dir / "level-assets" / f"{level}.asset",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def verify_legacy_batch(
    batch_dir: str | os.PathLike[str],
    levels: Sequence[int | str],
    tiers: Sequence[int],
    expected_probes: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    max_games: int,
) -> dict[str, Any]:
    """Verify snapshots and complete CSV coverage for one explicit batch."""
    root = Path(batch_dir)
    if not root.is_dir():
        raise LegacyBatchVerificationError(f"batch directory missing: {root}")

    level_keys = [str(level) for level in levels]
    tier_keys = sorted(int(tier) for tier in tiers)
    records = _summary_records(root)
    batch_wrs: dict[str, dict[str, float]] = {}
    batch_games: dict[str, dict[str, int]] = {}
    batch_records: dict[str, list[dict[str, Any]]] = {}

    for level in level_keys:
        expected = expected_probes.get(level)
        if expected is None:
            expected = expected_probes.get(str(level))
        if isinstance(expected, Mapping):
            expected = [
                expected.get(f"T{index}")
                if expected.get(f"T{index}") is not None
                else expected.get(str(index))
                for index in range(1, 6)
            ]
        if expected is None or len(expected) != 5 or any(item is None for item in expected):
            raise LegacyBatchVerificationError(f"expected five probe configs missing for L{level}")

        snapshot = _snapshot_path(root, level)
        actual = read_ddc_snapshot(snapshot)
        if len(actual) != 5:
            raise LegacyBatchVerificationError(
                f"L{level} asset snapshot has {len(actual)} tiers, expected 5"
            )
        for index, (got, want) in enumerate(zip(actual, expected), start=1):
            if _norm_config(got) != _norm_config(want):
                raise LegacyBatchVerificationError(
                    f"L{level} T{index} loaded asset differs from expected probe: "
                    f"got={_norm_config(got)} expected={_norm_config(want)}"
                )

        batch_wrs[level] = {}
        batch_games[level] = {}
        batch_records[level] = []
        for tier in tier_keys:
            key = (level, tier)
            if key not in records:
                raise LegacyBatchVerificationError(
                    f"summary artifact missing: L{level} T{tier}"
                )
            record = records[key]
            if record["totalGames"] > max_games:
                raise LegacyBatchVerificationError(
                    f"summary games exceed request: L{level} T{tier} "
                    f"{record['totalGames']} > {max_games}"
                )
            batch_wrs[level][f"T{tier}"] = record["wr"]
            batch_games[level][f"T{tier}"] = record["totalGames"]
            batch_records[level].append(record)

    return {
        "mode": "legacy",
        "batch_dir": str(root),
        "batch_wrs": batch_wrs,
        "batch_games": batch_games,
        "batch_records": batch_records,
        "asset_snapshots_verified": True,
        "artifact_count": len(level_keys) * len(tier_keys),
        "status": "accepted",
    }


def _candidate_from_token(repo: Path, token: str) -> Path | None:
    value = token.strip().strip('"').strip("'")
    if not value:
        return None
    direct = Path(value)
    candidates = [direct]
    if not direct.is_absolute():
        candidates.append(repo / "telemetry" / "bot" / value)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def resolve_legacy_batch_dir(
    repo: str | os.PathLike[str],
    stdout: str,
    *,
    started_at: float,
) -> Path:
    """Resolve an explicit directory returned by the legacy runner.

    No newest-directory or mtime selection is used. The BuildLogs pointer must
    be rewritten during this run, or stdout must contain an explicit Batch dir.
    """
    repo_path = Path(repo)
    pointer = repo_path / "BuildLogs" / "auto-batch-last-export.txt"
    if pointer.is_file() and pointer.stat().st_mtime >= started_at - 1:
        resolved = _candidate_from_token(repo_path, pointer.read_text(encoding="utf-8"))
        if resolved:
            return resolved

    for line in reversed((stdout or "").splitlines()):
        match = re.search(r"Batch dir:\s*(.+?)\s*$", line)
        if not match:
            continue
        resolved = _candidate_from_token(repo_path, match.group(1))
        if resolved:
            return resolved

    raise LegacyBatchVerificationError(
        "legacy batch directory was not explicitly reported; refusing directory guessing"
    )


__all__ = [
    "LegacyBatchVerificationError",
    "read_ddc_snapshot",
    "resolve_legacy_batch_dir",
    "verify_legacy_batch",
]
