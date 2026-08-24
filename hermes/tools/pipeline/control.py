"""V3 event store, pure reducer, and fail-closed Coordinator.

This module is deliberately independent from the legacy ``auto_loop`` entry
point.  P0.2 makes its public seams correct and testable first; later slices
route the legacy submit path through this module.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping


class PipelineBlocked(RuntimeError):
    """A preflight/guard/receipt condition prevented any runner side effect."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class IdempotencyConflict(RuntimeError):
    """The same idempotency key was reused for a different event payload."""


class EventStoreCorrupt(RuntimeError):
    """An events.jsonl middle record is invalid and cannot be safely skipped."""


class RunSpecImmutable(RuntimeError):
    """A run directory already has a different immutable run specification."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
        temp_name = fh.name
    os.replace(temp_name, path)


def _empty_level_state() -> dict[str, Any]:
    return {
        "status": "CREATED",
        "attempts_consumed": 0,
        "ingest_count": 0,
        "ingested_receipt_ids": [],
        "_attempts": {},
        "_consumed_attempt_ids": set(),
        "_blocked": False,
    }


def _block(state: dict[str, Any], reason: str) -> None:
    state["status"] = "ERROR_BLOCKED"
    state["block_reason"] = reason
    state["_blocked"] = True


def _same(*values: Any) -> bool:
    return bool(values) and all(value == values[0] for value in values[1:])


def _attempt_for(state: dict[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    attempt_id = str(event.get("attempt_id", ""))
    attempts = state["_attempts"]
    if attempt_id not in attempts:
        attempts[attempt_id] = {
            "submitted": False,
            "verified": False,
            "verification_status": None,
            "receipt_id": None,
            "request_plan_hash": None,
            "executed_plan_hash": None,
            "artifact_set_hash": None,
            "ingested": False,
            "generation_id": None,
            "judged": False,
        }
    return attempts[attempt_id]


def _decision_binding_ok(state: dict[str, Any], event: Mapping[str, Any]) -> bool:
    """Keep all later events bound to the validated planner decision."""
    expected_id = state.get("decision_id")
    if expected_id is None:
        return True
    if event.get("decision_id") != expected_id:
        _block(state, "decision_id_mismatch")
        return False
    for field in ("context_hash", "catalog_id", "probe_config_hash"):
        expected = state.get(field)
        if expected is not None and event.get(field) != expected:
            _block(state, f"decision_{field}_mismatch")
            return False
    return True


def _event_identity_valid(event: Mapping[str, Any]) -> bool:
    return all(str(event.get(field, "")).strip() for field in ("run_id", "level", "attempt_id"))


def reduce_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a per-level state projection from immutable V3 events.

    Idempotency is handled before transition processing.  A valid attempt is
    consumed only after the exact chain:

    ``SUBMITTED -> ARTIFACT_VERIFIED(status=accepted) -> INGESTED -> JUDGED``.

    Receipt, artifact-set, request-plan, executed-plan, and ingest-generation
    identities must agree across the chain.  Advisory post-review failures are
    deliberately state-neutral.
    """

    ordered: list[Mapping[str, Any]] = []
    seen_keys: dict[str, str] = {}
    for event in events:
        if not isinstance(event, Mapping):
            raise EventStoreCorrupt("event must be a mapping")
        key = str(event.get("idempotency_key", ""))
        payload_hash = str(event.get("payload_hash", ""))
        if not key or not payload_hash:
            raise EventStoreCorrupt("event missing idempotency_key or payload_hash")
        previous = seen_keys.get(key)
        if previous is not None:
            if previous != payload_hash:
                raise IdempotencyConflict(f"idempotency key reused with different payload: {key}")
            continue
        seen_keys[key] = payload_hash
        ordered.append(event)

    states: dict[str, dict[str, Any]] = {}
    run_ids: set[str] = set()

    for event in ordered:
        level = str(event.get("level", ""))
        run_id = str(event.get("run_id", ""))
        if not level:
            raise EventStoreCorrupt("event missing level")
        state = states.setdefault(level, _empty_level_state())
        kind = str(event.get("type", ""))
        if run_id:
            run_ids.add(run_id)

        if kind == "POST_REVIEW_FAILED":
            # Post-review is an advisory side branch.  It cannot retry Unity,
            # consume attempts, or overwrite an already-derived main state.
            continue

        if state["_blocked"]:
            continue

        if not _event_identity_valid(event):
            _block(state, "event_identity_missing")
            continue

        attempt = _attempt_for(state, event)
        attempt_id = str(event["attempt_id"])

        if kind == "CREATED":
            state["status"] = "CREATED"
            continue
        if kind == "SNAPSHOT_READY":
            state["status"] = "SNAPSHOT_READY"
            continue
        if kind in {"DECISION_READY", "DECISION_VALIDATED"}:
            decision_id = event.get("decision_id")
            if not decision_id:
                _block(state, "decision_identity_missing")
                continue
            state["decision_id"] = decision_id
            state["decision_revision"] = event.get("decision_revision", 1)
            for field in ("context_hash", "catalog_id", "probe_config_hash"):
                if field in event:
                    state[field] = event[field]
            state["status"] = kind
            continue

        if kind == "SUBMITTED":
            if not _decision_binding_ok(state, event):
                continue
            attempt["submitted"] = True
            attempt["request_plan_hash"] = event.get("request_plan_hash")
            state["status"] = "SUBMITTED"
            continue

        if kind == "ARTIFACT_VERIFIED":
            if not _decision_binding_ok(state, event):
                continue
            if not attempt["submitted"]:
                _block(state, "artifact_verified_without_submission")
                continue
            verification_status = event.get("verification_status")
            attempt["verification_status"] = verification_status
            attempt["receipt_id"] = event.get("batch_receipt_id")
            attempt["request_plan_hash"] = event.get("request_plan_hash")
            attempt["executed_plan_hash"] = event.get("executed_plan_hash")
            attempt["artifact_set_hash"] = event.get("accepted_artifact_set_hash")
            if verification_status != "accepted":
                # A partial/rejected/failed receipt can exist, but it may not
                # flow into ingest/judge.  Keeping it non-consumable is enough
                # until Coordinator.resume schedules only retry_pairs.
                state["status"] = "PARTIAL_PENDING" if verification_status == "partial" else "ERROR_BLOCKED"
                if verification_status != "partial":
                    state["_blocked"] = True
                    state["block_reason"] = "receipt_not_accepted"
                continue
            if not _same(
                event.get("request_plan_hash"),
                event.get("executed_plan_hash"),
            ):
                _block(state, "plan_hash_mismatch")
                continue
            if not _same(
                event.get("expected_artifact_set_hash"),
                event.get("accepted_artifact_set_hash"),
            ):
                _block(state, "artifact_set_mismatch")
                continue
            if not attempt["receipt_id"] or not attempt["artifact_set_hash"]:
                _block(state, "receipt_identity_missing")
                continue
            attempt["verified"] = True
            state["status"] = "ARTIFACT_VERIFIED"
            continue

        if kind == "INGESTED":
            if not _decision_binding_ok(state, event):
                continue
            if not attempt["submitted"] or not attempt["verified"]:
                _block(state, "ingest_without_accepted_receipt")
                continue
            receipt_id = event.get("batch_receipt_id")
            if not _same(receipt_id, attempt["receipt_id"]):
                _block(state, "ingest_receipt_mismatch")
                continue
            if not _same(
                event.get("request_plan_hash"), attempt["request_plan_hash"],
                event.get("executed_plan_hash"), attempt["executed_plan_hash"],
            ):
                _block(state, "ingest_plan_mismatch")
                continue
            if not _same(event.get("accepted_artifact_set_hash"), attempt["artifact_set_hash"]):
                _block(state, "ingest_artifact_set_mismatch")
                continue
            generation = event.get("ingest_generation_id")
            if not generation:
                _block(state, "ingest_generation_missing")
                continue
            if receipt_id in state["ingested_receipt_ids"]:
                # A new idempotency key cannot make the same receipt ingest a
                # second time.  It is a no-op, not a new attempt.
                continue
            state["ingested_receipt_ids"].append(receipt_id)
            state["ingest_count"] += 1
            attempt["ingested"] = True
            attempt["generation_id"] = generation
            state["status"] = "INGESTED"
            continue

        if kind == "JUDGED":
            if not _decision_binding_ok(state, event):
                continue
            if not attempt["submitted"] or not attempt["verified"] or not attempt["ingested"]:
                _block(state, "judge_without_ingest")
                continue
            if not _same(event.get("batch_receipt_id"), attempt["receipt_id"]):
                _block(state, "judge_receipt_mismatch")
                continue
            if not _same(event.get("consumed_generation_id"), attempt["generation_id"]):
                _block(state, "judge_generation_mismatch")
                continue
            if not _same(
                event.get("request_plan_hash"), attempt["request_plan_hash"],
                event.get("executed_plan_hash"), attempt["executed_plan_hash"],
            ):
                _block(state, "judge_plan_mismatch")
                continue
            if not _same(event.get("accepted_artifact_set_hash"), attempt["artifact_set_hash"]):
                _block(state, "judge_artifact_set_mismatch")
                continue
            result = event.get("result")
            if result not in {"合格", "接近", "不合格"}:
                _block(state, "unknown_judgment_result")
                continue
            if attempt_id not in state["_consumed_attempt_ids"]:
                state["_consumed_attempt_ids"].add(attempt_id)
                state["attempts_consumed"] = len(state["_consumed_attempt_ids"])
            attempt["judged"] = True
            if result == "合格":
                state["status"] = "VALIDATION_QUEUED"
            elif state["attempts_consumed"] >= 6:
                state["status"] = "AWAIT_REDESIGN_APPROVAL"
            else:
                state["status"] = "QUEUED_NEXT_ATTEMPT"
            continue

        _block(state, f"unknown_event_type:{kind}")

    public_levels: dict[str, dict[str, Any]] = {}
    for level, state in states.items():
        public_levels[level] = {
            key: value
            for key, value in state.items()
            if not key.startswith("_")
        }
    return {"run_ids": sorted(run_ids), "levels": public_levels}


class RunStore:
    """Append-only ``run.json`` / ``events.jsonl`` store.

    ``run.json`` is immutable after creation. ``summary.json`` is always a
    rebuildable projection, never a control input.
    """

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.run_path = self.root / "run.json"
        self.events_path = self.root / "events.jsonl"
        self.summary_path = self.root / "summary.json"
        self._recovery_status = "clean"
        self._truncated_offset: int | None = None

    def initialize(self, run_spec: Mapping[str, Any]) -> bool:
        self.root.mkdir(parents=True, exist_ok=True)
        normalized = json.loads(_canonical_json(dict(run_spec)))
        if self.run_path.exists():
            try:
                current = json.loads(self.run_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EventStoreCorrupt(f"invalid run.json: {exc}") from exc
            if _canonical_json(current) == _canonical_json(normalized):
                return False
            raise RunSpecImmutable("run.json already exists with a different specification")
        _atomic_json_write(self.run_path, normalized)
        return True

    def read_run_spec(self) -> dict[str, Any]:
        try:
            return json.loads(self.run_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise EventStoreCorrupt("run.json is missing")
        except (OSError, json.JSONDecodeError) as exc:
            raise EventStoreCorrupt(f"invalid run.json: {exc}") from exc

    def _read_events(self) -> list[dict[str, Any]]:
        self._recovery_status = "clean"
        self._truncated_offset = None
        if not self.events_path.exists():
            return []
        try:
            raw = self.events_path.read_bytes()
        except OSError as exc:
            raise EventStoreCorrupt(f"cannot read events.jsonl: {exc}") from exc
        if not raw:
            return []

        chunks = raw.splitlines(keepends=True)
        nonempty = [i for i, chunk in enumerate(chunks) if chunk.strip()]
        last_nonempty = nonempty[-1] if nonempty else -1
        events: list[dict[str, Any]] = []
        offset = 0
        for index, chunk in enumerate(chunks):
            stripped = chunk.strip()
            if not stripped:
                offset += len(chunk)
                continue
            try:
                decoded = json.loads(stripped.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                final_unterminated = index == last_nonempty and not chunk.endswith((b"\n", b"\r"))
                if final_unterminated:
                    self._recovery_status = "truncated_tail"
                    self._truncated_offset = offset
                    break
                raise EventStoreCorrupt(f"corrupt events.jsonl at record {index + 1}: {exc}") from exc
            if not isinstance(decoded, dict):
                raise EventStoreCorrupt(f"events.jsonl record {index + 1} is not an object")
            events.append(decoded)
            offset += len(chunk)
        return events

    def _repair_truncated_tail(self) -> None:
        if self._truncated_offset is None:
            return
        with self.events_path.open("r+b") as fh:
            fh.truncate(self._truncated_offset)
            fh.flush()
            os.fsync(fh.fileno())
        self._truncated_offset = None

    def append(self, event: Mapping[str, Any]) -> bool:
        if not isinstance(event, Mapping):
            raise EventStoreCorrupt("event must be a mapping")
        key = str(event.get("idempotency_key", ""))
        payload_hash = str(event.get("payload_hash", ""))
        if not key or not payload_hash:
            raise EventStoreCorrupt("event missing idempotency_key or payload_hash")
        existing = self._read_events()
        for prior in existing:
            if prior.get("idempotency_key") == key:
                if prior.get("payload_hash") == payload_hash:
                    return False
                raise IdempotencyConflict(f"idempotency key reused with different payload: {key}")
        self.root.mkdir(parents=True, exist_ok=True)
        self._repair_truncated_tail()
        sequence = max((int(item.get("seq", 0)) for item in existing), default=0) + 1
        record = dict(event)
        record["seq"] = sequence
        record["ts"] = _utc_now()
        record.setdefault("artifact_paths", [])
        if not isinstance(record["artifact_paths"], list):
            raise EventStoreCorrupt("artifact_paths must be a list")
        encoded = (_canonical_json(record) + "\n").encode("utf-8")
        with self.events_path.open("ab") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        # Summary is only a convenience projection. If it cannot be written,
        # the durable event is still valid and load_state will rebuild it.
        try:
            _atomic_json_write(self.summary_path, self.load_state())
        except Exception:
            pass
        return True

    def load_events(self) -> list[dict[str, Any]]:
        return self._read_events()

    def recovery_report(self) -> dict[str, Any]:
        self._read_events()
        return {"status": self._recovery_status}

    def load_state(self) -> dict[str, Any]:
        state = reduce_events(self._read_events())
        try:
            _atomic_json_write(self.summary_path, state)
        except Exception:
            pass
        return state


def _preflight_ok(result: Any) -> tuple[bool, str]:
    if isinstance(result, Mapping):
        code = result.get("returncode", 0)
        return int(code) == 0, str(result.get("stdout") or result.get("detail") or "")
    if isinstance(result, tuple) and len(result) >= 2:
        return bool(result[0]), str(result[1])
    return bool(result), ""


def _guard_ok(result: Any) -> tuple[bool, str]:
    if isinstance(result, Mapping):
        return bool(result.get("ok")), str(result.get("detail") or result.get("code") or "")
    if isinstance(result, tuple) and len(result) >= 2:
        return bool(result[0]), str(result[1])
    return bool(result), ""


class Coordinator:
    """Single-process fail-closed V3 orchestration seam.

    A runner is the only side-effecting dependency. It is invoked exactly after
    a successful preflight and every guard reports success.
    """

    def __init__(self, *, runner: Any, preflight: Any, guards: Iterable[Any], ingestor: Any = None):
        self.runner = runner
        self.preflight = preflight
        self.guards = list(guards)
        self.ingestor = ingestor

    def _authorize(self, request: Mapping[str, Any]) -> None:
        try:
            ok, detail = _preflight_ok(self.preflight(request))
        except Exception as exc:
            raise PipelineBlocked("PREFLIGHT_EXCEPTION", str(exc)) from exc
        if not ok:
            raise PipelineBlocked("PREFLIGHT_FAILED", detail)
        for guard in self.guards:
            try:
                ok, detail = _guard_ok(guard(request))
            except PipelineBlocked:
                raise
            except Exception as exc:
                raise PipelineBlocked("GUARD_EXCEPTION", str(exc)) from exc
            if not ok:
                code = detail.split()[0] if detail else "GUARD_BLOCKED"
                raise PipelineBlocked(code, detail)

    def run(self, request: Mapping[str, Any]) -> Any:
        self._authorize(request)
        return self.runner.run(dict(request))

    def resume(self, request: Mapping[str, Any]) -> dict[str, Any]:
        prior = request.get("prior_receipt")
        if not isinstance(prior, Mapping):
            raise PipelineBlocked("RESUME_RECEIPT_MISSING", "prior_receipt is required")
        identity = prior.get("identity")
        if not isinstance(identity, Mapping):
            raise PipelineBlocked("RESUME_RECEIPT_IDENTITY_MISSING")
        for field in ("run_id", "attempt_id"):
            if identity.get(field) != request.get(field):
                raise PipelineBlocked("RESUME_IDENTITY_MISMATCH", field)
        status = prior.get("status")
        if status == "accepted":
            return {"status": "already_accepted", "receipt": dict(prior)}
        if status != "partial":
            raise PipelineBlocked("RESUME_RECEIPT_INVALID", str(status))
        retry_pairs = prior.get("retry_pairs")
        if not isinstance(retry_pairs, list) or not retry_pairs:
            raise PipelineBlocked("RESUME_RETRY_PAIRS_MISSING")
        resumed = dict(request)
        resumed["execution_pairs"] = [list(pair) for pair in retry_pairs]
        resumed["resume_of_receipt"] = dict(prior)
        # Partial results are explicitly not ingested or judged; only missing
        # slots are run again using the exact same attempt identity.
        return {"status": "resubmitted_partial", "runner_receipt": self.run(resumed)}


def build_production_coordinator(*, runner: Any, preflight: Any) -> Coordinator:
    """Build the V3 Coordinator wired to production guard adapters.

    The concrete guard adapters are supplied by the P0.4 Policy slice.  This
    fallback remains intentionally conservative: a caller must provide an
    implementation through the normal production wrapper rather than silently
    bypassing guards.
    """
    from .policy import production_guards

    return Coordinator(runner=runner, preflight=preflight, guards=production_guards())
