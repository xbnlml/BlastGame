# V3 pipeline contract tests

Run from `hermes/`:

```bash
python -m unittest discover -s tests/pipeline -p 'test_*.py' -v
```

## P0.1 expected red state

The `tools.pipeline` package now exists only as a signature skeleton. Before the
P0.2–P0.4 green slices are implemented, the behavior tests must fail with one
of these explicit diagnostics:

- `V3 contract not implemented: EVENT_REDUCER_V1`
- `V3 contract not implemented: RUN_STORE_INITIALIZE_V1`
- `V3 contract not implemented: RUN_STORE_APPEND_V1`
- `V3 contract not implemented: BATCH_RECEIPT_V1`
- `V3 contract not implemented: COORDINATOR_RUN_V1`
- `V3 contract not implemented: COORDINATOR_RESUME_V1`
- `V3 contract not implemented: PRODUCTION_COORDINATOR_WIRING_V1`

`test_fixture_integrity.py` must stay green. Syntax errors, unreadable fixtures,
unexpected imports, absolute production paths, or an unrelated exception are
**not** acceptable red states.

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
