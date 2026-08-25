# Pipeline contract layer

The modules in this directory implement tested contracts for request identity,
receipts, provenance, RunStore events, ingestion generations and guarded
coordination. `role_contract.py` validates role manifests; `provenance.py`
binds Planner decisions to immutable request evidence.

**当前默认生产路径**仍是 `scripts/auto_loop.py` 的 legacy 单 Unity 串行批跑：
preflight/Warden → submit → asset/CSV 验收 → pool refresh → Judge。V3 contract
layer is retained as tested infrastructure and is not presented as the active
Unity submission path.

| Seam | Current contract ID | First green phase |
|---|---|---|
| `verify_batch_artifacts(bot_root, request)` | `BATCH_RECEIPT_V1` | P0.3 |
| `reduce_events(events)` | `EVENT_REDUCER_V1` | P0.2 |
| `RunStore.initialize/read_run_spec/append/load_events/recovery_report/load_state` | `RUN_STORE_*_V1` | P0.2 |
| `Coordinator.run/resume` | `COORDINATOR_RUN_V1` | P0.2 |
| `build_production_coordinator` | `PRODUCTION_COORDINATOR_WIRING_V1` | P0.4 |
| `verify_system_health(snapshot)` | `SYSTEM_HEALTH_GUARD_V1` | P0.4 |
| `PolicyEvaluator.evaluate(snapshot)` | declared with Policy slice | P0.4 |
| `build_decision_provenance/validate_decision_provenance` | `DECISION_PROVENANCE_V1` | P1 |

Public behavior is specified by `tests/pipeline/`; the full suite is expected to
stay green. Legacy production acceptance has its own tests in
`test_legacy_batch.py` and `test_auto_loop_guard_adapter.py`.

`slot` in a V3 batch receipt means the Unity execution slot reconstructed from
the historical numeric CSV `Tier` (`T1`–`T5`). It is intentionally separate from
the future Probe Designer's `P1`–`P5` decision slots; P→runtime-tier mapping is a
P0.3/P2 contract, not an implicit P0.1 assumption.
