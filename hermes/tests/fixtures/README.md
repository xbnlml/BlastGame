# Pipeline regression fixtures

These fixtures are deterministic, sanitized reproductions of BlastGame pipeline incidents.
They are test evidence, never tuning input, and must never be loaded into `stage-data`.

## `demo_replay.json`

- A fixed snapshot of real verified records for L86/L108/L119/L122, captured on 2026-08-25.
- `scripts/demo.py` recomputes selection and judgment from 117 records and compares the result with the accepted snapshot.
- `source_files` records SHA-256 for the 12 checked-in stage-data files; fixture tests verify both hashes and the exact record multiset.
- It contains tuning parameters, win rates, game counts, sources and timestamps, but no workstation paths, credentials, production fingerprints or Unity assets.
- It is read-only replay evidence and must never be merged back into the live tuning pool.

## Fidelity contract

The campaign-summary fixtures preserve the Unity `BlastBotExportCampaignSummaryRow.CsvHeader()` **17-column** schema, including numeric `Tier`. Board/deal fingerprints are stable synthetic SHA-256 values; timestamps, batch identities, and source board fingerprints are not production values. Each expected artifact is recorded explicitly in both the request and Unity receipt sidecar.

## `shared_csv_7_levels`

- Shape preserved from the real 2026-08-18 seven-level batch: five shared tier CSVs, each containing seven out-of-order level rows.
- `request.json` and `telemetry/bot/batch-expected/unity_receipt.json` bind 35 exact `(level, slot, tier, board_fingerprint, deal_fingerprint)` artifacts plus run/attempt/batch/plan/logic identity.
- Regression: a per-level directory glob reads only the last level embedded before `-Tn`, yielding 5/35 rather than 35/35 rows.

## `stale_latest_dir`

- Contains requested `batch-requested` and unrelated `batch-unrelated-newer`.
- Tests set mtimes explicitly after copying the fixture; request identity, never mtime or directory name, determines the consumed batch.

## `partial_batch`

- Request expects four pairs; receipt preserves accepted `60/T1` and explicitly reports three missing pairs.
- Recovery must reuse the same attempt and submit only the missing pairs. It may not discard `60/T1` or rerun it.

## `asset_db_mismatch_l138`

- Canonical minimal all-slot L138 asset/database mismatch health fixture.
- It must block before Unity starts and record `asset_db_fingerprint_mismatch`.

## Safety

- No absolute workstation paths, credentials, production fingerprints, or production board data.
- Tests copy fixtures to a temporary directory before mutation; checked-in fixtures remain immutable.
