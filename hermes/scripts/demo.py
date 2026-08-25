#!/usr/bin/env python3
"""Replay a checked-in BlastGame evidence snapshot without Unity or live files."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


HERMES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERMES))

from tools.find_best_combo import find_best_monotonic  # noqa: E402
from tools.judge_level import check_judgment  # noqa: E402


DEFAULT_FIXTURE = HERMES / "tests" / "fixtures" / "demo_replay.json"


class ReplayError(ValueError):
    pass


def load_fixture(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReplayError(f"fixture unavailable: {path}: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayError(f"fixture is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ReplayError("fixture schema_version must be 1")
    if not isinstance(data.get("levels"), list) or not data["levels"]:
        raise ReplayError("fixture must contain at least one level")
    return data, hashlib.sha256(raw).hexdigest()


def replay_level(entry: dict[str, Any]) -> dict[str, Any]:
    try:
        level = int(entry["level"])
        difficulty = str(entry["difficulty"])
        targets = [float(value) for value in entry["targets"]]
        records = list(entry["records"])
        expected = entry["expected"]
        expected_wrs = [float(value) for value in expected["wrs"]]
        expected_verdict = str(expected["verdict"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplayError(f"malformed level evidence: {entry!r}") from exc
    if len(targets) != 5 or len(expected_wrs) != 5 or not records:
        raise ReplayError(f"L{level}: targets/expected must have five tiers and records cannot be empty")

    results = find_best_monotonic(records, targets, top_n=1, difficulty=difficulty)
    if not results:
        raise ReplayError(f"L{level}: selector produced no combination")
    chosen = results[0][2]
    actual_wrs = [round(float(record["wr"]), 4) for record in chosen]
    verdict, reasons = check_judgment(
        {f"T{index + 1}": value for index, value in enumerate(actual_wrs)},
        difficulty,
        targets,
    )
    wrs_match = all(abs(actual - expected) <= 1e-6 for actual, expected in zip(actual_wrs, expected_wrs))
    return {
        "level": level,
        "difficulty": difficulty,
        "targets": targets,
        "records": len(records),
        "games": sum(int(record.get("totalGames", 0)) for record in records),
        "actual_wrs": actual_wrs,
        "verdict": verdict,
        "reasons": reasons,
        "passed": wrs_match and verdict == expected_verdict,
        "expected_wrs": expected_wrs,
        "expected_verdict": expected_verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay real checked-in BlastGame tuning evidence")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args(argv)
    try:
        fixture, evidence_hash = load_fixture(args.fixture)
        results = [replay_level(entry) for entry in fixture["levels"]]
    except ReplayError as exc:
        print(f"OFFLINE REPLAY ERROR: {exc}", file=sys.stderr)
        return 2

    print("BlastGame offline replay — checked-in real verified evidence")
    print(f"evidence_sha256={evidence_hash}")
    print("| Level | Difficulty | Records | Games | Targets | Selected WR | Verdict | Result |")
    print("|---:|---|---:|---:|---|---|---|---|")
    for result in results:
        targets = "/".join(f"{value:g}" for value in result["targets"])
        wrs = "/".join(f"{value:g}" for value in result["actual_wrs"])
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"| L{result['level']} | {result['difficulty']} | {result['records']} | "
            f"{result['games']} | {targets} | {wrs} | {result['verdict']} | {status} |"
        )
        if not result["passed"]:
            print(
                f"  expected WR={result['expected_wrs']} verdict={result['expected_verdict']}"
            )

    passed = all(result["passed"] for result in results)
    print(f"OFFLINE REPLAY {'PASS' if passed else 'FAIL'}: {sum(r['passed'] for r in results)}/{len(results)} levels")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())