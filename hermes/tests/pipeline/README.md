# V3 pipeline contract tests

Run from `hermes/`:

```bash
python -m unittest discover -s tests/pipeline -p 'test_*.py' -v
```

## Current baseline

All tests are expected to pass. The suite covers both the V3 contract layer and
the active legacy acceptance adapter; a contract test is not evidence that V3
is the default Unity path. `test_fixture_integrity.py` keeps checked-in evidence
free of production paths and credentials. `test_demo_replay.py` proves the
public replay works without a Unity workspace. `test_tool_smoke.py` runs against the
configured live workspace when present and reports an explicit skip otherwise.

## Public seams under test

- `verify_batch_artifacts(bot_root, request)`
- `reduce_events(events)`
- `RunStore.initialize/read_run_spec/append/load_events/recovery_report/load_state`
- `Coordinator.run(request)` / `Coordinator.resume(request)`
- `build_production_coordinator(runner, preflight)`

`reduce_events(events)` is the sole pure reducer. `RunStore.load_state()` is
only its durable projection; neither test nor implementation should introduce a
second reducer named `RunStore.reduce()`.

The tests specify externally observable behavior. They must not assert private helper calls, log text, implementation data structures, or exact file-write order.

## Business invariants

- Batch identity comes from the request, never newest-directory heuristics.
- Shared tier CSV rows are verified per `(level, slot, tier, board fingerprint, deal fingerprint)`.
- Request and Unity receipt must bind the same run/attempt/batch/plan/logic identity.
- A partial receipt retains accepted rows and retries only its declared missing pairs.
- Receipt `slot` is the historical Unity execution slot derived from numeric CSV
  `Tier` (`T1`–`T5`); it is **not** the future Probe Designer `P1`–`P5` slot.
  P→runtime-tier mapping is deliberately deferred to P0.3/P2.
- Only artifact-verified, ingested, judged attempts consume the six-attempt budget.
- `接近` consumes an effective attempt and queues more tuning; it never queues import.
- `post_batch_review` is non-blocking and cannot trigger a Unity rerun.
- Preflight/Guard failure or exception is fail-closed and starts Unity zero times.
- Event idempotency keys prevent duplicate state transitions.
- Reusing an idempotency key with a different payload is a fail-closed conflict.
