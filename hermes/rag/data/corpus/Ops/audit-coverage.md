# Agent Pipeline Tools Coverage Audit

**Audited:** 2026-07-30  
**Project:** `<HERMES_ROOT>`
**Full report:** `project-state/audit_report.md`

## Agent Pipeline Architecture

```
agent_data.py ──→ 刷新 stage-data 数据池 + level_sig 校验 + asset 完整性
agent_analyze.py ──→ filter_verified + find_best_monotonic 选最优 + 内联探针设计
agent_review.py ──→ 四元组验证 (read_ddc) + check_gaps (judge_level) + Excel 交叉验证
judge_level.py ──→ 按 blastgame-judgment 标准 (②合格③硬违规④档差审美⑤分级) + 6 轮追踪
```

`submit_batch_unity.py` 步骤6自动串联 `agent_analyze` → `agent_review`。

## Coverage Matrix

### ✅ Covered by Agent Pipeline

| Tool | Entry Point | Role in Pipeline |
|------|------------|------------------|
| `tools/agent_data.py` | `--levels` | Data Agent standalone |
| `tools/agent_analyze.py` | `--levels --filter-verified` | Analyze Agent standalone |
| `tools/agent_review.py` | `--combo-file` | Review Agent standalone |
| `tools/judge_level.py` | `check_judgment()` | Called by agent_review for gap checking |
| `tools/asset_patcher.py` | `level_sig()`, `verify_integrity()`, `read_ddc()` | Called by agent_data + agent_review |
| `tools/data/pool.py` | `filter_verified()`, `find_best_monotonic()`, `dedup_records()` | Called by agent_analyze + judge_level |
| `tools/data/adapters/excel_target.py` | `get_target()` | Called by agent_analyze + agent_review |
| `tools/dump_level_pools.py` | `build_level_pools()`, `dump_all_pools()` | Called by agent_data.refresh_pools() |
| `tools/get_level_pool.py` | `parse_levels()` | Called by agent_data |
| `project-state/_rounds.json` | `_load_rounds()`, `_save_rounds()`, `inc_round()` | Called by judge_level for 6-round tracking |

### ❌ Not in Agent Pipeline (Gaps)

| Tool | Status | Impact |
|------|--------|--------|
| `design_probes.py` | agent_analyze has inline `_design_probes()` (40 lines) that doesn't use design_probes.py (164 lines with bot400 baseline, phase2 candidate scoring, in-range priority) | Probe quality degraded |
| `apply_probes.py` | Not called by any agent | Asset configs not auto-written before bot runs |
| `probe_configs.json` | agent_analyze probes not persisted | Cannot reuse across rounds |
| `preflight.py` | submit_batch_unity has inline asset checks but missing board conflict, Editor conflict, data source preview | Missing guardrails |
| `post_batch_review.py` | Called by submit_batch_unity step 5 but has `source_tier` bug | Batch analysis broken |
| `monitor_bot.py` | submit_batch_unity has own monitoring; monitor_bot as standalone not integrated | Redundant but unused |
| `read_target_wr.py` | Agents use excel_target.py instead | Redundant, can archive |

### ⚠️ Overlap / Redundancy

| Tool | Overlaps With | Recommendation |
|------|--------------|----------------|
| `find_best_combo.py` | agent_analyze (both call pool.find_best_monotonic) | Keep as manual CLI diagnostic tool |
| `validate_combo.py` | judge_level.py + agent_review.py (has own validate() not using judgment-rules.md) | Migrate to judge_level standards or archive |
| `archive/pick_best_combos.py` | find_best_combo/agent_analyze (hardcoded levels 172-184) | Already archived |

### 📦 Diagnostic/Utility (Not in Pipeline by Design)

| Tool | Purpose | Pipeline Integration Needed? |
|------|---------|------------------------------|
| `check_unity.py` | Check if Unity process running | No — skill explicitly prohibits |
| `restart_unity.py` | Start/restart Unity | No — skill explicitly prohibits |
| `diff_state.py` | Compare asset vs Excel vs pool | No — diagnostic only |
| `state_snapshot.py` | Global state snapshot from board.md | No — diagnostic only |
| `stage_status.py` | 51-200 status summary | No — diagnostic only |
| `viz_level.py` | Plotly scatter/span charts | No — diagnostic only |
| `retire_level.py` | Write time fence for retired levels | No — manual decision, not agent-automated |

## Known Bugs (from Audit)

### P0: post_batch_review.py `source_tier` KeyError
**File:** `tools/post_batch_review.py`, line 162  
**Bug:** References `rec['source_tier']` but records use key `'tier'` (see line 119)  
**Fix:** Change `source_tier` → `tier` in both occurrences on line 162

### P1: agent_analyze._design_probes() inferior to design_probes.py
**File:** `tools/agent_analyze.py`, lines 33-68  
**Issue:** Inline `_design_probes()` is 40-line simplified version. design_probes.py (164 lines) has:
- Bot400 baseline evaluation before scoring candidates
- Phase2 candidate scoring with improvement metrics
- In-range priority sorting
- Gap-filling with designed probes when phase2 candidates insufficient
**Fix:** agent_analyze should import/use design_probes.design(lv) or its logic should be backported.

## Re-audit 2026-07-30 (Comprehensive Project Audit)

Follow-up audit triggered by user request for full project review. New findings beyond the initial coverage audit:

### 🔴 P0: agent_data.py NOT wired into submit_batch_unity pipeline

`submit_batch_unity.py` step 4 calls `dump_level_pools.py` directly to refresh pools, **completely bypassing agent_data.py**. This means:
- `level_sig()` signature verification never runs in the automated pipeline
- `verify_integrity()` asset checks never run
- Pool refresh happens but without the safety layer agent_data provides

**Current flow:**
```
submit_batch_unity: dump_level_pools → post_batch_review → agent_analyze → agent_review
                    ↑ no agent_data here
```

**Should be:**
```
submit_batch_unity: dump_level_pools → agent_data --no-refresh → post_batch_review → agent_analyze → agent_review
```

The `--no-refresh` flag avoids duplicate pool refresh (dump_level_pools already did it), letting agent_data focus on signature verification + integrity checks.

### 🔴 P0: _rounds.json round tracking never triggered by agent pipeline

`agent_review.py` calls only `judge_level.check_judgment()` (line 27-28) for gap checking. It does NOT call `judge_level.judge_with_rounds()` which manages:
- `inc_round(lv)` — increment round counter
- `reset_round(lv)` — reset on合格
- 6-round MAX_ROUNDS enforcement
- Auto-改关卡 decision at round 6

As a result, `project-state/_rounds.json` currently only tracks 4 levels (136, 176, 178, 184) that were manually judged. The agent pipeline has zero awareness of round state.

### 🟡 P1: blastgame-judgment 规则双轨制

`blastgame-judgment/SKILL.md` (v1.0.0) and `references/judgment-rules.md` define **different rule systems**:

| Rule | SKILL.md | judgment-rules.md |
|------|---------|-------------------|
| Normal gap | T1→T3≥15pp, T3→T5≥15pp, T3≥60% | Tiered by WR bracket (≥50%: 15-35pp, 30-50%: 10-20pp, <30%: 10-15pp) |
| Hard/SuperHard gap | 各档差≥10pp | Same tiered system |
| 硬性违规 | gap<5%, gap>40%(Hard), 倒挂>1%, T3<60%(Normal), <5%档, <10%档>1 | gap<5%, 倒挂>1%, <5%档 |
| 偏离≤2pp直接合格 | Yes | Not in rules (uses 接近 tier) |

`judge_level.py` follows SKILL.md. `judgment-rules.md` is unused in code. **Recommendation:** remove or deprecate judgment-rules.md to prevent confusion.

### 🟡 P2: 数据优先级阈值三源不一致

| Source | Top-tier threshold |
|--------|-------------------|
| MEMORY.md L21 | `bot≥300 > summary≥300` |
| blastgame-pool-data-integrity SKILL.md | `bot(400局) > summary(400)` |
| blastgame-judgment SKILL.md table | `bot≥400=0, 300-399=1` |

Three authoritative sources disagree on the top priority cutoff (300 vs 400 games). **Recommendation:** align on `bot≥400 / summary≥400` as uniform top tier.

### 🟡 P2: design_probes.py methodology mismatch with multi-tier-designer skill

`blastgame-multi-tier-designer` prescribes a need-driven probe design flow (calculate target gaps → mark deviation tier → allocate slots to gaps). `design_probes.py` uses a different approach: evaluate bot400 baseline → score phase2 candidates by pool improvement → pick top candidates. Three key gaps:
1. No 16-preset ratios system used for R1 wide-spectrum probes
2. No 5-slot allocation rules based on gap analysis
3. No of bidirectional probing direction detection

### 🟢 P3: Deprecated tools still present

`check_unity.py` and `restart_unity.py` are explicitly prohibited by skill rules (MEMORY.md L5: "不需手动 check_unity/restart_unity", level-optimizer SKILL.md L31: "禁止主动启动 Unity"). Both should be archived to `tools/archive/`.
