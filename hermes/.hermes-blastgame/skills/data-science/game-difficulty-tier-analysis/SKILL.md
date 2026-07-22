---
name: game-difficulty-tier-analysis
description: "Analyze multi-tier difficulty configurations (T1-T5) for casual/mobile games from bot telemetry, validate against design rules (档差/gap, 倒挂/inversion, T3 anchor), and produce structured pass/fail assessments."
version: 1.0.0
author: Hermes Agent
created: 2026-06-30
tags: [game-design, difficulty-tuning, bot-telemetry, data-analysis, tier-validation]
category: data-science
---

# Game Difficulty Tier Analysis (多档位难度分析)

Analyze and validate multi-tier (T1–T5) dynamic difficulty configurations from bot telemetry data. Produces rule-graded pass/fail assessments for game designers.

## When to Use

- A game project has multi-tier difficulty configs (Normal with 3 effective tiers, Hard/SuperHard with 5)
- Bot batch-run CSV files exist under `telemetry/bot/` with columns: level, DifficultyLevel, winkate, winCount, failCount
- You need to check which levels pass/fail a set of design rules (档差, T3锚点, 倒挂)
- The deliverable is a structured assessment table + recommended next actions

**Do NOT use when:** The task is purely about running the bot itself (use the bot-orchestrator skill), or about the Unity asset patching workflow (use the project's own scripts).

## Workflow

### Phase 1: Gather Data

1. **Read project rules** — find the RULES.md (or equivalent) that defines:
   - Per-difficulty T3 anchor ranges (Normal ≥60%, Hard 30-60%, SuperHard ≤50%)
   - 档差 (tier gap) requirements: ≥15% for high-WR tiers, ≥7% for low-WR tiers, ≥5% hard floor
   - 倒挂 (inversion) rules: adjacent tiers must be monotonically decreasing
   - Any入库放宽口径 (acceptable relaxations)

2. **Find bot telemetry** — search `telemetry/bot/` for the latest campaign-summary CSVs
   - Each CSV is one tier: columns = LevelGroup, level, DifficultyLevel, winkate, winCount, failCount
   - Multiple CSVs needed: one file per tier (T1.csv, T2.csv, etc.)
   - Note the run count per tier (from directory name / auto-batch-result.json)

3. **Check existing handoff docs and manifest JSON** — HANDOFF-*.md, manifest.json, auto-batch-request.json for:
   - Which levels are done/pending/failed
   - Baseline bot WR values
   - Variant definitions (A=primary, B=fallback)
   - Expected label WR from optimizer

4. **Read existing Excel** — `手动挑配置记录.xlsx` for previously recorded configs
   - Each level has 6 rows: header + T1–T5 with WR, sd, sc, ratios, of

### Phase 2: Build Comparison Table

For each level in the scope, build a table:

| Tier | Baseline Bot WR | New Bot WR (300-400 runs) | Expected (label) | Pass? |
|------|----------------|--------------------------|-------------------|-------|
| T1 | baseline% | new% (if available) | label% | rule check |
| T2 | ... | ... | ... | ... |
| T3 | ... | ... | ... | ... |
| T4 | ... | ... | ... | ... |
| T5 | ... | ... | ... | ... |

**Key data sources to cross-reference:**
- T1/T2: may use baseline (400-game) data if variant didn't change them
- T3/T4/T5: use latest 300-game bot run from the fix-combo-verify batch
- Normal levels: T2 = T1 (same config), T5 = T4 (same config) — verify in CSV
- Hard/SuperHard: check all 5 tiers are distinct

### Phase 3: Validate Against Rules

Check each level against these rules (in priority order):

#### Hard Violations (必须修):
1. **R-H1 (倒挂/Inversion)**: Any adjacent-tier WR inverted (Tn < T(n+1) by >1%). Mark FAIL immediately.
2. **R-H2 (<5% gap)**: Any effective adjacent gap < 5%. Mark FAIL.
3. **R-H3 (T3 anchor)**: T3 outside per-difficulty range. Mark FAIL.

#### Soft Issues (待优化):
4. **R-S1**: High-end gap (T1-T2 or T1-T3 for Normal) < 20% (accept ≥15%)
5. **R-S2**: Mid-low gap (T4-T5, or T3-T5 for Normal) < 10% (accept ≥7%)
6. **R-S3**: Normal T1-T5 span < 10%
7. **R-S4**: Hard/SuperHard T1-T5 span < 10%

**入库放宽口径 (Acceptable relaxations):**
- 档差标准降低: high-end ≥15% (from 20%), low-end ≥7% (from 10%)
- 硬性下限仍为5%
- T3锚点不放松

#### Normal Special Rules:
- Only 3 effective configs: T1=T2, T4=T5
- Only check gaps: T1→T3, T3→T5 (and overall T1→T5)
- T3 ≥ 60%
- Bot验收只跑 tiersCsv=1,3,5

### Phase 4: Produce Assessment

For each level, output:

```
L** (Difficulty) — **判定：合格/不合格** 🟢/🔴
- 基线问题: original failure reason
- 改法: what was changed
- 预期: expected label WR
- 实装结果: actual bot WR with comparison
- 根因 (if failed): why it didn't work
- 下一步 (if failed): recommended next action
```

Group into:
- ✅ **合格 (Pass)** — can write to Excel + asset
- 🔄 **待复验 (Pending retest)** — need variant B or stronger config
- 🔴 **不合格 (Fail)** — needs different approach (probe, optimizer, or new slot data)

### Phase 5: Common Pitfalls

| Pitfall | Symptom | Solution |
|---------|---------|----------|
| 交换方案无效 (swap fails) | T4↔T5 swap still leaves inversion | Need variant B with different probe slots, not just swapping |
| 跨关借参不可靠 (cross-level parameter reuse) | Same config works at L87 but fails at L99 | Different boards have different RNG behavior — each level needs its own probe data |
| T5降不下去 (T5 won't go low enough) | Normal T4/T5 stuck at 53%+ | Need a genuinely harder probe slot (lower sd, different ratio distribution) |
| Batch run was baseline, not patched | Bot results match baseline values | Check auto-batch-result.json timestamp vs patch time; ensure --patch ran before batch |
| 300-run vs 400-run mismatch | T1/T2 data from different run | Document which run each tier's data came from; note statistical uncertainty |
| Normal levels showing T2≠T1 | T2 data differs from T1 | Either the config wasn't properly merged (should be identical), or it's noise within 0-1% |
