"""Runtime adapter joining explicit Unity receipts to RunStore generations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .control import RunStore
from .ingest import AtomicGenerationStore
from .provenance import validate_decision_provenance


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _normalize_judge_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize receipt WRs to the percentage-point unit used by Judge."""
    normalized = dict(record)
    raw = float(normalized.get("wr", normalized.get("win_rate")))
    normalized["wr"] = raw * 100.0 if abs(raw) <= 1.0 else raw
    return normalized


def _load_accepted_generation(
    root: str | Path,
    level: str | int,
    *,
    expected_logic_version: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Load a prior generation only after verifying its accepted event chain."""
    root_path = Path(root)
    run_spec = json.loads((root_path / "run.json").read_text(encoding="utf-8"))
    if expected_logic_version and run_spec.get("logic_version") != expected_logic_version:
        raise ValueError(f"logic version mismatch for prior run {root_path}")

    store = RunStore(root_path)
    events = store.load_events()
    state = store.load_state()
    level_key = str(level)
    level_state = state.get("levels", {}).get(level_key)
    if not isinstance(level_state, Mapping) or level_state.get("status") == "ERROR_BLOCKED":
        raise ValueError(f"prior run is blocked or missing L{level_key}: {root_path}")

    accepted_ids = {
        str(event.get("batch_receipt_id"))
        for event in events
        if str(event.get("level")) == level_key
        and event.get("type") == "ARTIFACT_VERIFIED"
        and event.get("verification_status") == "accepted"
        and event.get("batch_receipt_id")
    }
    ingested = {
        str(event.get("batch_receipt_id")): event
        for event in events
        if str(event.get("level")) == level_key
        and event.get("type") == "INGESTED"
        and event.get("batch_receipt_id")
    }
    candidates = [
        (index, receipt_id, ingested[receipt_id])
        for index, event in enumerate(events)
        if str(event.get("level")) == level_key
        and event.get("type") == "ARTIFACT_VERIFIED"
        and event.get("verification_status") == "accepted"
        and (receipt_id := str(event.get("batch_receipt_id", ""))) in accepted_ids
        and receipt_id in ingested
    ]
    if not candidates:
        raise ValueError(f"no accepted+ingested generation for L{level_key}: {root_path}")
    _, receipt_id, ingest_event = candidates[-1]
    generation_id = str(ingest_event.get("ingest_generation_id", ""))
    if not generation_id:
        raise ValueError(f"prior ingest has no generation for L{level_key}: {root_path}")

    manifest_path = root_path / "ingest" / "generations" / generation_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("identity", {}).get("logic_version") != run_spec.get("logic_version"):
        raise ValueError(f"prior generation identity mismatch: {manifest_path}")
    ingest_receipt = {
        "generation_id": generation_id,
        "receipt_fingerprint": manifest.get("receipt_fingerprint"),
    }
    records = AtomicGenerationStore(root_path / "ingest").load_for_judge(ingest_receipt, level_key)
    return [_normalize_judge_record(record) for record in records], generation_id


class V3RunRuntime:
    """Persist a V3 run and consume each accepted receipt at most once."""

    def __init__(self, root: str | Path, request: Mapping[str, Any]):
        self.root = Path(root)
        self.request = dict(request)
        self.store = RunStore(self.root)
        self.ingest_store = AtomicGenerationStore(self.root / "ingest")
        self.receipt: dict[str, Any] | None = None
        self.ingest_receipt: dict[str, Any] | None = None
        self._consumed_generation_ids: dict[str, list[str]] = {}

    def start(self) -> None:
        spec = {
            "version": "RUN_SPEC_V1",
            "run_id": self.request["run_id"],
            "attempt_id": self.request.get("attempt_id"),
            "logic_version": self.request.get("logic_version"),
            "request_plan_hash": self.request.get("request_plan_hash"),
            "levels": list(self.request.get("levels", [])),
            "tiers": list(self.request.get("tiers", [])),
            "policy_id": "rules.json",
            "decision_provenance": self.request.get("decision_provenance", {}),
        }
        provenance_by_level = self.request.get("decision_provenance", {})
        if self.request.get("require_decision_provenance") and not isinstance(provenance_by_level, Mapping):
            raise ValueError("decision provenance is required for this run")
        for level in spec["levels"]:
            if isinstance(provenance_by_level, Mapping) and str(level) in provenance_by_level:
                provenance = provenance_by_level[str(level)]
                if not isinstance(provenance, Mapping):
                    raise ValueError(f"invalid decision provenance for level {level}")
                validate_decision_provenance(
                    provenance,
                    level=level,
                    round_num=int(provenance.get("round", 0)),
                    probes=(self.request.get("probes", {}) or {}).get(str(level), {}),
                )
        self.store.initialize(spec)
        for level in spec["levels"]:
            self._append({"type": "CREATED", "level": str(level), "attempt_id": "run"}, f"created:{level}")
            self._append({"type": "SNAPSHOT_READY", "level": str(level), "attempt_id": "run"}, f"snapshot:{level}")
            if isinstance(provenance_by_level, Mapping) and str(level) in provenance_by_level:
                provenance = provenance_by_level[str(level)]
                self._append({
                    "type": "DECISION_VALIDATED",
                    "level": str(level),
                    "attempt_id": self.request["attempt_id"],
                    **dict(provenance),
                }, f"decision:{level}:{provenance['decision_id']}")

    def submitted(self) -> None:
        for level in self.request.get("levels", []):
            self._append({
                "type": "SUBMITTED", "level": str(level),
                "attempt_id": self.request["attempt_id"],
                "request_plan_hash": self.request["request_plan_hash"],
                **self._decision_fields(level),
            }, f"submitted:{level}:{self.request['attempt_id']}")

    def finish(self, receipt: Mapping[str, Any]) -> dict[str, Any] | None:
        self.receipt = dict(receipt)
        if receipt.get("status") != "accepted":
            return None
        receipt_id = receipt.get("batch_receipt_id")
        if not receipt_id:
            raise ValueError("accepted receipt missing batch_receipt_id")
        expected_set = receipt.get("expected_artifact_set_hash")
        accepted_set = receipt.get("accepted_artifact_set_hash")
        if not expected_set or expected_set != accepted_set:
            raise ValueError("accepted receipt artifact set is not complete")
        artifacts = receipt.get("artifacts")
        if not isinstance(artifacts, list):
            raise ValueError("accepted receipt artifacts missing")
        records: dict[str, list[dict[str, Any]]] = {}
        for artifact in artifacts:
            level = str(artifact["level"])
            record = dict(artifact)
            raw_win_rate = float(artifact["win_rate"])
            record.update({
                "source": "summary",
                # Pool/Judge records use percentage points (e.g. 80.0),
                # while campaign-summary winkate is a ratio (e.g. 0.8).
                "wr": raw_win_rate * 100.0 if abs(raw_win_rate) <= 1.0 else raw_win_rate,
                "totalGames": max(1, int(artifact.get("total_games", 0))),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "boardFingerprint": artifact["board_fingerprint"],
            })
            records.setdefault(level, []).append(record)
        self.ingest_receipt = self.ingest_store.ingest(receipt, records)
        for level in records:
            base = {
                "type": "ARTIFACT_VERIFIED", "level": level,
                "attempt_id": self.request["attempt_id"],
                "batch_receipt_id": receipt_id,
                "verification_status": "accepted",
                "request_plan_hash": receipt["request_plan_hash"],
                "executed_plan_hash": receipt["executed_plan_hash"],
                "expected_artifact_set_hash": expected_set,
                "accepted_artifact_set_hash": accepted_set,
                **self._decision_fields(level),
            }
            self._append(base, f"verified:{level}:{receipt_id}")
            self._append({
                "type": "INGESTED", "level": level,
                "attempt_id": self.request["attempt_id"],
                "batch_receipt_id": receipt_id,
                "ingest_generation_id": self.ingest_receipt["generation_id"],
                "request_plan_hash": receipt["request_plan_hash"],
                "executed_plan_hash": receipt["executed_plan_hash"],
                "accepted_artifact_set_hash": accepted_set,
                **self._decision_fields(level),
            }, f"ingested:{level}:{receipt_id}")
        return self.ingest_receipt

    def judged(
        self,
        level: str | int,
        result: str,
        *,
        supporting_generation_ids: Iterable[str] | None = None,
    ) -> None:
        if not self.receipt or not self.ingest_receipt or self.receipt.get("status") != "accepted":
            raise ValueError("cannot judge without accepted receipt and ingest")
        level = str(level)
        payload = {
            "type": "JUDGED", "level": level,
            "attempt_id": self.request["attempt_id"],
            "batch_receipt_id": self.receipt["batch_receipt_id"],
            "consumed_generation_id": self.ingest_receipt["generation_id"],
            "result": result,
            "request_plan_hash": self.receipt["request_plan_hash"],
            "executed_plan_hash": self.receipt["executed_plan_hash"],
            "accepted_artifact_set_hash": self.receipt["accepted_artifact_set_hash"],
            **self._decision_fields(level),
        }
        supporting = [str(value) for value in (supporting_generation_ids or []) if str(value)]
        if supporting:
            payload["supporting_generation_ids"] = supporting
        self._append(payload, f"judged:{level}:{self.receipt['batch_receipt_id']}")

    def state(self) -> dict[str, Any]:
        return self.store.load_state()

    def records_for_judge(
        self,
        level: str | int,
        supporting_run_roots: Iterable[str | Path] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.ingest_receipt:
            raise ValueError("Judge requires an accepted ingest receipt")
        level_key = str(level)
        records = [
            _normalize_judge_record(record)
            for record in self.ingest_store.load_for_judge(self.ingest_receipt, level_key)
        ]
        generation_ids = [str(self.ingest_receipt["generation_id"])]
        fingerprints = {
            str(record.get("board_fingerprint", record.get("boardFingerprint", "")))
            for record in records
            if record.get("board_fingerprint", record.get("boardFingerprint", ""))
        }
        for prior_root in supporting_run_roots or []:
            prior_records, prior_generation_id = _load_accepted_generation(
                prior_root,
                level_key,
                expected_logic_version=self.request.get("logic_version"),
            )
            if prior_generation_id in generation_ids:
                continue
            prior_fingerprints = {
                str(record.get("board_fingerprint", record.get("boardFingerprint", "")))
                for record in prior_records
                if record.get("board_fingerprint", record.get("boardFingerprint", ""))
            }
            if fingerprints and prior_fingerprints and fingerprints != prior_fingerprints:
                raise ValueError(f"board fingerprint mismatch across generations for L{level_key}")
            records.extend(prior_records)
            fingerprints.update(prior_fingerprints)
            generation_ids.append(prior_generation_id)
        self._consumed_generation_ids[level_key] = generation_ids
        return records

    def consumed_generation_ids(self, level: str | int) -> list[str]:
        return list(self._consumed_generation_ids.get(str(level), []))

    def _decision_fields(self, level: str | int) -> dict[str, Any]:
        provenance = (self.request.get("decision_provenance", {}) or {}).get(str(level), {})
        if not isinstance(provenance, Mapping):
            return {}
        return {
            key: provenance[key]
            for key in ("decision_id", "context_hash", "catalog_id", "probe_config_hash")
            if key in provenance
        }

    def _append(self, payload: Mapping[str, Any], key: str) -> None:
        record = dict(payload)
        record.update({"run_id": self.request["run_id"], "idempotency_key": key})
        record["payload_hash"] = _hash(record)
        self.store.append(record)
