# V3 pipeline public seams

P0/P1 contracts are implemented incrementally.  `role_contract.py` validates
role manifests; `provenance.py` binds Planner decisions to the immutable
RunStore/request chain.  Remaining unimplemented operations still raise
`ContractNotImplemented(<contract-id>)`.

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

The public behavior is specified by `tests/pipeline/`. Existing `auto_loop.py`
remains a known legacy path until P0.2 routes its actual submit path through this
Coordinator. P0.1 tests therefore specify the target V3 entry contract; they do
not claim W09/preflight is already fail-closed in the legacy path.

`slot` in a V3 batch receipt means the Unity execution slot reconstructed from
the historical numeric CSV `Tier` (`T1`–`T5`). It is intentionally separate from
the future Probe Designer's `P1`–`P5` decision slots; P→runtime-tier mapping is a
P0.3/P2 contract, not an implicit P0.1 assumption.
