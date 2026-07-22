# Telemetry Comparison Patterns

Concrete patterns for comparing baseline vs new bot runs during difficulty tier analysis.

## Data Source Tracking

When bot runs come from different batches with different run counts, **document each tier's provenance**:

```
T1/T2: baseline round3, 400 games (batch 12-45-49)
T3/T4/T5: primary variant A, 300 games (batch 17-17-14)
```

This matters because:
- 400g data has ~5% margin; 300g has ~5.6% margin (at p≈50%)
- Adjacent tiers from different runs may have slightly different noise floors
- Always check auto-batch-result.json to confirm the run succeeded

## Baseline vs New Result Table

For a level with config changes, build a 7-column table:

| Tier | Baseline Bot | New Bot | Expected | Delta | Pass? | Note |
|------|-------------|---------|----------|-------|-------|------|
| T1   | 92.0%       | (same)  | 92%      | 0     | —     | unchanged |
| T2   | 65.0%       | (same)  | 65%      | 0     | —     | unchanged |
| T3   | 62.7%       | 60.0%   | 60.5%    | -2.7  | ✅    | probe.S3 dropped WR as expected |
| T4   | 25.0%       | 24.3%   | 25%      | -0.7  | ✅    | stable |
| T5   | 11.2%       | 14.7%   | 11.2%    | +3.5  | ⚠️    | higher than expected, within noise |

## Key Differences Between 300g and 400g Data

| Aspect | 300g | 400g |
|--------|------|------|
| p≈50% margin | ~5.6% | ~5.0% |
| p≈80% margin | ~4.5% | ~4.0% |
| Use case | 入库验收 (default) | 入库复核 (marginal cases) |
| Retest signal | If a gap is 5-10%, bump to 400g for confirmation |

## Cross-Batch Consistency Check

When two batches ran the same tiers (e.g. 17-04-44 and 17-17-14 both ran T3), compare:

```
L87 T3: 48.7% (17-04-44) vs 63.0% (17-17-14)  → 14% gap → patch state differed
L93 T3: 61.7% (17-04-44) vs 61.7% (17-17-14)  → identical → same patch state
```

A >5% difference between runs labeled with the same tag usually means:
1. The asset patch was applied between the two runs
2. Or the first run used old asset state (warmup / mis-patched)

## 入库 Assessment Matrix

| Rule | Condition | Check For |
|------|-----------|-----------|
| R-H1 | Tn < T(n+1) by >1% | Any Hard level with T5 > T4 → fail |
| R-H2 | Any gap < 5% | Normal T3≈T4=T5 → fail |
| R-H3 | T3 out of range | Normal T3 < 60%, Hard T3 < 30% or > 60% |
| R-S1 | High-end gap < 15% | Hard T1-T2 < 15% is borderline |
| R-S2 | Mid-low gap < 7% | Normal T3-T5 < 7% is borderline |
