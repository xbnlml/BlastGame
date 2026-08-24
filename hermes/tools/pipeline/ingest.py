#!/usr/bin/env python3
"""Atomic V3 ingest generations bound to an accepted batch receipt."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


class IngestBlocked(RuntimeError):
    """A receipt/generation cannot safely enter the judge data path."""


class IngestReplayConflict(IngestBlocked):
    """One receipt identity attempted to write different data."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    raw = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
        temp = fh.name
    os.replace(temp, path)


def _accepted_rows(batch_receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if batch_receipt.get("status") != "accepted":
        raise IngestBlocked("receipt must be accepted before ingest")
    identity = batch_receipt.get("identity")
    if not isinstance(identity, Mapping):
        raise IngestBlocked("receipt identity is missing")
    for field in ("run_id", "attempt_id", "batch_id", "request_plan_hash", "executed_plan_hash", "logic_version"):
        if not identity.get(field):
            raise IngestBlocked(f"receipt identity missing {field}")
    rows = batch_receipt.get("artifacts")
    if not isinstance(rows, list) or not rows:
        raise IngestBlocked("accepted receipt artifacts are missing")
    identities = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise IngestBlocked("receipt artifact is invalid")
        key = (str(row.get("level")), str(row.get("slot")), str(row.get("deal_fingerprint")))
        if "None" in key or not all(key):
            raise IngestBlocked("receipt artifact identity missing")
        if key in identities:
            raise IngestBlocked("receipt artifact duplicate")
        identities.add(key)
    return rows


class AtomicGenerationStore:
    """Writes a generation privately, verifies hashes, then atomically exposes it.

    The mutable ``current.json`` pointer is a convenience only. A Judge receives
    the immutable ingest receipt and loads the named generation, so a later
    refresh cannot silently change what an attempt is judged against.
    """

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.generations = self.root / "generations"
        self.receipts = self.root / "receipts"
        self.pointer = self.root / "current.json"

    def ingest(self, batch_receipt: Mapping[str, Any], records_by_level: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
        artifacts = _accepted_rows(batch_receipt)
        identity = dict(batch_receipt["identity"])
        receipt_fingerprint = _sha256({
            "identity": identity,
            "artifacts": artifacts,
        })
        normalized_records: dict[str, list[dict[str, Any]]] = {}
        artifact_pairs = {(str(row["level"]), str(row["slot"])) for row in artifacts}
        for level, records in records_by_level.items():
            level_key = str(level)
            if not isinstance(records, list):
                raise IngestBlocked(f"records for L{level_key} must be list")
            normalized_records[level_key] = [dict(record) for record in records]
        if set(normalized_records) != {str(row["level"]) for row in artifacts}:
            raise IngestBlocked("records levels do not exactly match accepted receipt levels")
        # Every pool record emitted by the adapter carries its originating slot
        # and deal fingerprint. This prevents an unrelated telemetry row from
        # being consumed as this attempt's data.
        for level, records in normalized_records.items():
            seen_slots = set()
            for record in records:
                pair = (str(record.get("level", level)), str(record.get("slot", "")))
                if pair not in artifact_pairs:
                    raise IngestBlocked(f"unbound record {pair}")
                if str(record.get("deal_fingerprint", "")) != next(
                    str(a["deal_fingerprint"])
                    for a in artifacts if (str(a["level"]), str(a["slot"])) == pair
                ):
                    raise IngestBlocked(f"deal fingerprint mismatch for {pair}")
                seen_slots.add(pair)
            expected_for_level = {pair for pair in artifact_pairs if pair[0] == level}
            if seen_slots != expected_for_level:
                raise IngestBlocked(f"records do not cover accepted slots for L{level}")

        payload_hash = _sha256(normalized_records)
        receipt_index = self.receipts / f"{receipt_fingerprint}.json"
        if receipt_index.exists():
            prior = json.loads(receipt_index.read_text(encoding="utf-8"))
            if prior.get("payload_hash") != payload_hash:
                raise IngestReplayConflict("same receipt identity has different ingest payload")
            return dict(prior["ingest_receipt"])

        generation_id = f"gen-{receipt_fingerprint[:16]}-{payload_hash[:12]}"
        final_dir = self.generations / generation_id
        temp_dir = self.generations / f".tmp-{generation_id}-{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=False)
        try:
            files: dict[str, dict[str, str]] = {}
            for level, records in sorted(normalized_records.items()):
                relative = f"levels/{level}.json"
                path = temp_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = _canonical(records)
                path.write_bytes(raw)
                files[level] = {"path": relative, "sha256": _sha256(raw)}
            manifest = {
                "version": "INGEST_GENERATION_V1",
                "generation_id": generation_id,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_hash": payload_hash,
                "identity": identity,
                "files": files,
            }
            _atomic_json(temp_dir / "manifest.json", manifest)
            if final_dir.exists():
                existing = json.loads((final_dir / "manifest.json").read_text(encoding="utf-8"))
                if existing.get("payload_hash") != payload_hash:
                    raise IngestReplayConflict("generation id collision with different payload")
                shutil.rmtree(temp_dir)
            else:
                self.generations.mkdir(parents=True, exist_ok=True)
                os.replace(temp_dir, final_dir)
            ingest_receipt = {
                "version": "INGEST_RECEIPT_V1",
                "generation_id": generation_id,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_hash": payload_hash,
                "identity": identity,
                "artifact_paths": [files[level]["path"] for level in sorted(files)],
            }
            _atomic_json(receipt_index, {
                "payload_hash": payload_hash,
                "ingest_receipt": ingest_receipt,
            })
            _atomic_json(self.pointer, {
                "generation_id": generation_id,
                "receipt_fingerprint": receipt_fingerprint,
            })
            return ingest_receipt
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def load_for_judge(self, ingest_receipt: Mapping[str, Any], level: str | int) -> list[dict[str, Any]]:
        """Load exactly the receipt-bound records after verifying every hash."""
        if not isinstance(ingest_receipt, Mapping):
            raise IngestBlocked("Judge requires an ingest receipt")
        generation_id = ingest_receipt.get("generation_id")
        receipt_fingerprint = ingest_receipt.get("receipt_fingerprint")
        if not generation_id or not receipt_fingerprint:
            raise IngestBlocked("ingest receipt identity missing")
        directory = self.generations / str(generation_id)
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IngestBlocked(f"generation manifest unavailable: {exc}") from exc
        if manifest.get("receipt_fingerprint") != receipt_fingerprint:
            raise IngestBlocked("ingest receipt does not bind this generation")
        entry = manifest.get("files", {}).get(str(level))
        if not isinstance(entry, Mapping):
            raise IngestBlocked(f"generation has no L{level}")
        path = directory / str(entry.get("path", ""))
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise IngestBlocked(f"generation data unavailable: {exc}") from exc
        if _sha256(raw) != entry.get("sha256"):
            raise IngestBlocked("generation artifact checksum mismatch")
        try:
            records = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IngestBlocked(f"generation data invalid: {exc}") from exc
        if not isinstance(records, list):
            raise IngestBlocked("generation records must be list")
        return records
