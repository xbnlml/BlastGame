"""Exact V3 batch request/receipt verification for Unity campaign-summary CSVs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping


class ArtifactVerificationError(RuntimeError):
    """Fail-closed receipt rejection with a stable machine-readable code."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


IDENTITY_FIELDS = (
    "run_id", "attempt_id", "batch_id", "request_plan_hash",
    "executed_plan_hash", "logic_version",
)
CSV_REQUIRED_COLUMNS = {
    "level", "Tier", "BoardFingerprint", "DealFingerprint", "winkate",
}


def _pair(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["level"]), str(row["slot"])


def _artifact_identity(row: Mapping[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        str(row["level"]), str(row["slot"]), int(row["tier"]),
        str(row["board_fingerprint"]), str(row["deal_fingerprint"]),
    )


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactVerificationError(code, f"missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactVerificationError(code, f"invalid: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ArtifactVerificationError(code, f"object expected: {path}")
    return data


def _normal_identity(raw: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in IDENTITY_FIELDS if field not in raw or raw[field] in (None, "")]
    if missing:
        raise ArtifactVerificationError("RECEIPT_IDENTITY_MISMATCH", f"missing identity: {missing}")
    return {field: raw[field] for field in IDENTITY_FIELDS}


def _validate_identity(request: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    expected = _normal_identity(request)
    actual = _normal_identity(receipt)
    if expected != actual:
        raise ArtifactVerificationError("RECEIPT_IDENTITY_MISMATCH", "request and receipt identity differ")
    if expected["request_plan_hash"] != expected["executed_plan_hash"]:
        raise ArtifactVerificationError("PLAN_HASH_MISMATCH", "request and executed plan hashes differ")
    return expected


def _expected_by_pair(request: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = request.get("expected_artifacts")
    if not isinstance(rows, list) or not rows:
        raise ArtifactVerificationError("REQUEST_ARTIFACTS_INVALID", "expected_artifacts is required")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ArtifactVerificationError("REQUEST_ARTIFACTS_INVALID", "artifact must be object")
        try:
            _artifact_identity(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactVerificationError("REQUEST_ARTIFACTS_INVALID", str(exc)) from exc
        pair = _pair(raw)
        if pair in result:
            raise ArtifactVerificationError("REQUEST_ARTIFACTS_INVALID", f"duplicate expected pair: {pair}")
        result[pair] = dict(raw)
    return result


def _validate_receipt_artifacts(
    expected: Mapping[tuple[str, str], Mapping[str, Any]], receipt: Mapping[str, Any]
) -> dict[tuple[str, str], dict[str, Any]]:
    rows = receipt.get("artifacts")
    if not isinstance(rows, list):
        raise ArtifactVerificationError("RECEIPT_ARTIFACT_MISMATCH", "artifacts is required")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ArtifactVerificationError("RECEIPT_ARTIFACT_MISMATCH", "artifact must be object")
        try:
            pair = _pair(raw)
            identity = _artifact_identity(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactVerificationError("RECEIPT_ARTIFACT_MISMATCH", str(exc)) from exc
        if pair in result:
            raise ArtifactVerificationError("RECEIPT_ARTIFACT_MISMATCH", f"duplicate receipt pair: {pair}")
        expected_row = expected.get(pair)
        if expected_row is None or identity != _artifact_identity(expected_row):
            raise ArtifactVerificationError("RECEIPT_ARTIFACT_MISMATCH", f"identity mismatch: {pair}")
        result[pair] = dict(raw)
    return result


def _read_csv_artifacts(batch_dir: Path, expected: Mapping[tuple[str, str], Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    files = sorted(batch_dir.rglob("campaign-summary-*.csv"))
    if not files:
        raise ArtifactVerificationError("CSV_MISSING", f"no campaign summary under {batch_dir}")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for path in files:
        try:
            with path.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames or not CSV_REQUIRED_COLUMNS.issubset(reader.fieldnames):
                    raise ArtifactVerificationError("CSV_SCHEMA_INVALID", str(path))
                for row in reader:
                    try:
                        tier = int(row["Tier"])
                    except (TypeError, ValueError) as exc:
                        raise ArtifactVerificationError("CSV_ARTIFACT_MISMATCH", f"invalid tier in {path}") from exc
                    pair = str(row["level"]), f"T{tier}"
                    if pair in result:
                        raise ArtifactVerificationError("DUPLICATE_ARTIFACT", f"duplicate CSV pair: {pair}")
                    expected_row = expected.get(pair)
                    if expected_row is None:
                        raise ArtifactVerificationError("UNREQUESTED_ARTIFACT", f"unexpected CSV pair: {pair}")
                    actual = {
                        "level": str(row["level"]),
                        "slot": f"T{tier}",
                        "tier": tier,
                        "board_fingerprint": str(row["BoardFingerprint"]),
                        "deal_fingerprint": str(row["DealFingerprint"]),
                    }
                    # Preserve the real campaign-summary measurements when
                    # present.  The identity verifier only needs the five
                    # fields above, while atomic ingest/Judge needs the
                    # four-tuple and exact win/loss denominator.
                    optional = {
                        "level_group": "LevelGroup",
                        "sd": "startDifficulty",
                        "sc": "shuffleSplitCount",
                        "ratios": "shuffleSplitRatios",
                        "of": "shuffleOverflowFactor",
                        "win_count": "winCount",
                        "fail_count": "failCount",
                    }
                    for target, column in optional.items():
                        if column in row and row[column] not in (None, ""):
                            actual[target] = row[column]
                    if _artifact_identity(actual) != _artifact_identity(expected_row):
                        raise ArtifactVerificationError("CSV_ARTIFACT_MISMATCH", f"identity mismatch: {pair}")
                    try:
                        actual["win_rate"] = float(row["winkate"])
                    except (TypeError, ValueError) as exc:
                        raise ArtifactVerificationError("CSV_ARTIFACT_MISMATCH", f"invalid win rate: {pair}") from exc
                    try:
                        actual["total_games"] = int(actual.get("win_count", 0)) + int(actual.get("fail_count", 0))
                    except (TypeError, ValueError):
                        actual["total_games"] = 0
                    result[pair] = actual
        except ArtifactVerificationError:
            raise
        except OSError as exc:
            raise ArtifactVerificationError("CSV_READ_FAILED", f"{path}: {exc}") from exc
    return result


def _pairs(rows: Any) -> set[tuple[str, str]]:
    if not isinstance(rows, list):
        return set()
    pairs: set[tuple[str, str]] = set()
    for item in rows:
        if isinstance(item, Mapping):
            pairs.add((str(item.get("level")), str(item.get("slot"))))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            pairs.add((str(item[0]), str(item[1])))
    return pairs


def receipt_win_rates(receipt: Mapping[str, Any], levels: list[int] | None = None) -> dict[str, dict[str, float]]:
    """Extract measured WRs from the explicitly accepted receipt artifacts.

    The receipt is already bound to one request and one batch's raw CSV rows;
    unlike the legacy report path, this function never discovers a directory by
    mtime or chooses a "latest" batch.
    """
    if not isinstance(receipt, Mapping):
        return {}
    allowed = {str(level) for level in levels} if levels is not None else None
    result: dict[str, dict[str, float]] = {}
    artifacts = receipt.get("artifacts", [])
    if not isinstance(artifacts, list):
        return result
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        level = str(artifact.get("level", ""))
        slot = str(artifact.get("slot", ""))
        if not level or not slot or (allowed is not None and level not in allowed):
            continue
        raw = artifact.get("win_rate", artifact.get("winkate"))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        # campaign-summary stores winkate as 0..1; tolerate already-percent
        # values from older receipt writers without changing the source value.
        percent = value * 100.0 if abs(value) <= 1.0 else value
        result.setdefault(level, {})[slot] = round(percent, 1)
    return result


def receipt_games(receipt: Mapping[str, Any], levels: list[int] | None = None) -> dict[str, dict[str, int]]:
    """Extract exact games played per level/slot from the same receipt."""
    if not isinstance(receipt, Mapping):
        return {}
    allowed = {str(level) for level in levels} if levels is not None else None
    result: dict[str, dict[str, int]] = {}
    artifacts = receipt.get("artifacts", [])
    if not isinstance(artifacts, list):
        return result
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        level = str(artifact.get("level", ""))
        slot = str(artifact.get("slot", ""))
        if not level or not slot or (allowed is not None and level not in allowed):
            continue
        raw = artifact.get("total_games")
        if raw in (None, ""):
            try:
                raw = int(artifact.get("win_count", 0)) + int(artifact.get("fail_count", 0))
            except (TypeError, ValueError):
                continue
        try:
            result.setdefault(level, {})[slot] = int(raw)
        except (TypeError, ValueError):
            continue
    return result


def verify_batch_artifacts(bot_root: str | Path, request: Mapping[str, Any]) -> dict[str, Any]:
    """Verify exactly one requested Unity batch and return an accepted/partial receipt.

    ``bot_root`` is the telemetry/bot root. The batch directory is selected only
    from ``request['batch_id']``; mtime and newest-directory heuristics are never
    consulted. Every accepted row is bound to request identity, Unity receipt,
    and a raw CSV row.
    """

    if not isinstance(request, Mapping):
        raise ArtifactVerificationError("REQUEST_INVALID", "request must be object")
    identity = _normal_identity(request)
    if identity["request_plan_hash"] != identity["executed_plan_hash"]:
        raise ArtifactVerificationError("PLAN_HASH_MISMATCH", "request plan hashes differ")
    batch_dir = Path(bot_root) / str(identity["batch_id"])
    if not batch_dir.is_dir():
        raise ArtifactVerificationError("BATCH_NOT_FOUND", str(batch_dir))
    receipt = _read_json(batch_dir / "unity_receipt.json", "RECEIPT_READ_FAILED")
    identity = _validate_identity(request, receipt)
    expected = _expected_by_pair(request)
    receipt_artifacts = _validate_receipt_artifacts(expected, receipt)
    csv_artifacts = _read_csv_artifacts(batch_dir, expected)

    raw_status = str(receipt.get("status", ""))
    if raw_status in {"completed", "accepted"}:
        if set(receipt_artifacts) != set(expected):
            raise ArtifactVerificationError("RECEIPT_ARTIFACT_MISMATCH", "completed receipt missing expected artifact")
        if set(csv_artifacts) != set(expected):
            missing = sorted(set(expected) - set(csv_artifacts))
            raise ArtifactVerificationError("CSV_MISSING", f"missing rows: {missing}")
        artifacts = [csv_artifacts[pair] for pair in sorted(expected)]
        return {
            "status": "accepted",
            "identity": identity,
            "artifacts": artifacts,
            "missing_pairs": [],
            "retry_pairs": [],
        }

    if raw_status == "partial":
        accepted_pairs = set(receipt_artifacts)
        expected_pairs = set(expected)
        missing_pairs = _pairs(receipt.get("missing_pairs"))
        if accepted_pairs & missing_pairs or accepted_pairs | missing_pairs != expected_pairs:
            raise ArtifactVerificationError("RECEIPT_ARTIFACT_MISMATCH", "partial receipt partition is invalid")
        if set(csv_artifacts) != accepted_pairs:
            raise ArtifactVerificationError("CSV_ARTIFACT_MISMATCH", "partial CSV rows differ from accepted receipt rows")
        ordered_accepted = [csv_artifacts[pair] for pair in sorted(accepted_pairs)]
        ordered_missing = [list(pair) for pair in sorted(missing_pairs)]
        return {
            "status": "partial",
            "identity": identity,
            "accepted_artifacts": ordered_accepted,
            "missing_pairs": ordered_missing,
            "retry_pairs": ordered_missing,
        }

    raise ArtifactVerificationError("RECEIPT_STATUS_INVALID", raw_status)
