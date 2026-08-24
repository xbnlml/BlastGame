"""Build and bind V3 Unity execution requests without mtime directory discovery."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence

from .batch_run import ArtifactVerificationError, _read_csv_artifacts


IDENTITY_FIELDS = (
    "run_id", "attempt_id", "batch_id", "request_plan_hash",
    "executed_plan_hash", "logic_version",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
        temp = fh.name
    os.replace(temp, path)


def _safe_batch_id(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if not value or len(value) > 96 or any(ch not in allowed for ch in value):
        raise ValueError("batch_id must be 1-96 chars of [A-Za-z0-9_-]")
    return value


def _logic_version_default() -> str:
    from tools.get_level_pool import LOGIC_VERSION_SINCE
    return LOGIC_VERSION_SINCE


def _plan_payload(artifacts: Sequence[Mapping[str, Any]], logic_version: str) -> dict[str, Any]:
    return {
        "version": "UNITY_EXECUTION_PLAN_V1",
        "logic_version": logic_version,
        "artifacts": [
            {
                "level": str(row["level"]), "slot": str(row["slot"]),
                "tier": int(row["tier"]),
                "board_fingerprint": str(row["board_fingerprint"]),
                "deal_fingerprint": str(row["deal_fingerprint"]),
            }
            for row in sorted(artifacts, key=lambda row: (int(row["level"]), int(row["tier"])))
        ],
    }


def execution_plan_hash(artifacts: Sequence[Mapping[str, Any]], logic_version: str) -> str:
    """Return the canonical execution-plan hash used on both sides of Unity."""
    return _sha256(_plan_payload(artifacts, logic_version))


def artifact_set_hash(artifacts: Sequence[Mapping[str, Any]]) -> str:
    """Hash only the row identity fields, excluding measured WR values."""
    return _sha256([
        {
            "level": str(row["level"]), "slot": str(row["slot"]),
            "tier": int(row["tier"]),
            "board_fingerprint": str(row["board_fingerprint"]),
            "deal_fingerprint": str(row["deal_fingerprint"]),
        }
        for row in sorted(artifacts, key=lambda row: (int(row["level"]), int(row["tier"])))
    ])


def _official_asset_plan(levels: Sequence[int]) -> list[dict[str, Any]]:
    from tools.asset_patcher import _asset_path

    helper = Path(__file__).with_name("asset_execution_plan.mjs")
    asset_paths = [str(_asset_path(int(level))) for level in levels]
    result = subprocess.run(
        ["node", str(helper), *asset_paths], capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if result.returncode != 0:
        raise ArtifactVerificationError("ASSET_EXECUTION_PLAN_FAILED", (result.stderr or result.stdout)[-500:])
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ArtifactVerificationError("ASSET_EXECUTION_PLAN_FAILED", "invalid helper JSON") from exc
    if not parsed.get("ok") or not isinstance(parsed.get("levels"), list):
        raise ArtifactVerificationError("ASSET_EXECUTION_PLAN_FAILED", str(parsed.get("error", "unknown")))
    return [dict(tier) for level in parsed["levels"] for tier in level.get("tiers", [])]


def build_unity_request(
        *, levels: Sequence[int], tiers: Sequence[int], run_id: str, attempt_id: str,
        batch_id: str | None = None, logic_version: str | None = None,
        games: int = 400, adaptive_stop: bool = True, strategy: str = "scoring_opt_vg",
        worker_count: int = 7, bayes_min_runs: int = 60) -> dict[str, Any]:
    """Build a request from official pre-run asset fingerprints.

    The result intentionally contains all expected slot identities before Unity
    starts.  It carries no credentials and writes nothing until ``write_request``
    is called by the submit adapter.
    """
    unique_levels = sorted({int(level) for level in levels})
    selected_tiers = sorted({int(tier) for tier in tiers})
    if not unique_levels or any(level < 1 for level in unique_levels):
        raise ValueError("levels must be nonempty positive integers")
    if not selected_tiers or any(tier < 1 or tier > 5 for tier in selected_tiers):
        raise ValueError("tiers must be within 1..5")
    if not run_id or not attempt_id:
        raise ValueError("run_id and attempt_id are required")
    batch = _safe_batch_id(batch_id or f"v3-{uuid.uuid4().hex}")
    logic = logic_version or _logic_version_default()
    all_artifacts = _official_asset_plan(unique_levels)
    expected = [item for item in all_artifacts if int(item["tier"]) in selected_tiers]
    if len(expected) != len(unique_levels) * len(selected_tiers):
        raise ArtifactVerificationError("ASSET_EXECUTION_PLAN_FAILED", "selected slot count mismatch")
    plan_hash = execution_plan_hash(expected, logic)
    return {
        "version": "UNITY_REQUEST_V1",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "batch_id": batch,
        "request_plan_hash": plan_hash,
        "executed_plan_hash": plan_hash,
        "logic_version": logic,
        "levels": [str(level) for level in unique_levels],
        "tiers": selected_tiers,
        "games": int(games),
        "adaptive_stop": bool(adaptive_stop),
        "strategy": strategy,
        "worker_count": int(worker_count),
        "bayes_min_runs": int(bayes_min_runs),
        "expected_artifacts": expected,
    }


def write_request(path: str | os.PathLike[str], request: Mapping[str, Any]) -> None:
    _atomic_json(Path(path), dict(request))


def _read_unity_marker(batch_dir: Path, request: Mapping[str, Any]) -> None:
    marker_path = batch_dir / "v3-unity-run.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactVerificationError("UNITY_MARKER_MISSING", str(marker_path)) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactVerificationError("UNITY_MARKER_INVALID", str(exc)) from exc
    for field in ("run_id", "attempt_id", "batch_id", "request_plan_hash"):
        if marker.get(field) != request.get(field):
            raise ArtifactVerificationError("UNITY_MARKER_IDENTITY_MISMATCH", field)


def write_receipt_from_batch(batch_dir: str | os.PathLike[str], request: Mapping[str, Any]) -> dict[str, Any]:
    """Bind actual CSV artifacts to an explicit request-root and persist receipt."""
    directory = Path(batch_dir)
    if directory.name != str(request.get("batch_id")):
        raise ArtifactVerificationError("BATCH_DIRECTORY_IDENTITY_MISMATCH", str(directory))
    _read_unity_marker(directory, request)
    expected = {(str(row["level"]), str(row["slot"])): dict(row) for row in request.get("expected_artifacts", [])}
    if not expected:
        raise ArtifactVerificationError("REQUEST_ARTIFACTS_INVALID", "expected_artifacts missing")
    actual = _read_csv_artifacts(directory, expected)
    actual_plan_hash = execution_plan_hash(list(actual.values()), str(request["logic_version"]))
    expected_pairs = set(expected)
    actual_pairs = set(actual)
    status = "accepted" if actual_pairs == expected_pairs else "partial"
    # For a partial run, the intended execution plan remains the immutable
    # request plan; successful rows are separately partitioned below.
    if status == "accepted" and actual_plan_hash != request["request_plan_hash"]:
        raise ArtifactVerificationError("PLAN_HASH_MISMATCH", "actual CSV plan differs from request plan")
    identity = {field: request[field] for field in IDENTITY_FIELDS}
    receipt_artifacts = [actual[pair] for pair in sorted(actual)]
    receipt_id = _sha256({"identity": identity, "artifacts": receipt_artifacts})
    receipt: dict[str, Any] = {
        "version": "UNITY_RECEIPT_V1",
        "status": status,
        "batch_receipt_id": receipt_id,
        "expected_artifact_set_hash": artifact_set_hash(list(expected.values())),
        "accepted_artifact_set_hash": artifact_set_hash(receipt_artifacts),
        "identity": identity,
        **identity,
        "artifacts": receipt_artifacts,
    }
    if status == "partial":
        missing = [list(pair) for pair in sorted(expected_pairs - actual_pairs)]
        receipt["missing_pairs"] = missing
    _atomic_json(directory / "unity_receipt.json", receipt)
    return receipt
