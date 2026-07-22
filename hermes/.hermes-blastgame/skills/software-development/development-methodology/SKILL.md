---
name: development-methodology
description: "Development processes: TDD, systematic debugging, spikes, code simplification, pre-commit review."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [testing, tdd, debugging, spike, code-review, pre-commit, simplify, methodology]
---

# Development Methodology — Unified Guide

Five essential development processes. Use the right one for the situation.

| Process | Use when... | Core Principle |
|---------|-------------|----------------|
| **TDD** | Building a new feature or fixing a bug | Write failing test first, then minimal code |
| **Debugging** | Something is broken and you need root cause | Find cause before attempting fix |
| **Spike** | Validating an idea before committing | Build a throwaway, get a verdict |
| **Simplify** | Cleaning up after implementation | Three parallel reviewers for reuse/quality/efficiency |
| **Review** | Before committing or pushing | Independent reviewer, static scan, quality gates |

---

## Section 1: Test-Driven Development

**Iron Law:** NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST. Write code before the test? Delete it. Start over.

### Red-Green-Refactor Cycle

1. **RED** — Write one minimal failing test
   - One behavior per test, clear descriptive name
   - Real code, not mocks (unless unavoidable)
   - Test behavior, not implementation

2. **Verify RED** — Watch it fail
   ```bash
   pytest tests/test_feature.py::test_name -v
   ```
   Check: test fails for expected reason (feature missing, not typo). If it passes immediately, test is wrong.

3. **GREEN** — Write minimal code to pass
   - Nothing extra. No logging, no edge cases, no refactoring
   - Cheating is OK in GREEN — hardcode, copy-paste, duplicate. Fix in REFACTOR.

4. **Verify GREEN** — Watch it pass + check no regressions
   ```bash
   pytest tests/test_feature.py::test_name -v
   pytest tests/ -q
   ```

5. **REFACTOR** — Clean up while staying green
   - Remove duplication, improve names, extract helpers
   - If tests fail: undo immediately, take smaller steps

### Avoid Horizontal Slices
Do NOT write all tests then all code. Use vertical tracer bullets:
```
RED→GREEN: test1→impl1, RED→GREEN: test2→impl2
```

### With Subagent Delegation
```python
delegate_task(
    goal="Implement [feature] using strict TDD",
    context="1. Write failing test FIRST. 2. Run test to verify it fails. 3. Write minimal code. 4. Verify pass. 5. Refactor. 6. Commit.",
    toolsets=['terminal', 'file']
)
```

### Rationalizations to Reject
| Excuse | Reality |
|--------|---------|
| "Too simple to test" | Simple code breaks. Test takes 30s. |
| "I'll test after" | Tests-after prove nothing (pass immediately) |
| "Already manually tested" | Ad-hoc ≠ systematic |
| "TDD will slow me down" | TDD is faster than debugging |
| "Existing code has no tests" | Add tests for code you touch |

---

## Section 2: Systematic Debugging

**Iron Law:** NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.

### The Feedback Loop Rule
Create a tight loop that can go red on the exact symptom and green when fixed. A tight loop is fast, deterministic, and specific.

### Four Phases

#### Phase 1: Root Cause Investigation
- Read error messages carefully
- Build a tight feedback loop (test, curl, CLI, browser, or harness)
- Check recent changes: `git log -10`, `git diff`
- For multi-component: add diagnostic instrumentation at each boundary
- Trace data flow upstream to find the source

#### Phase 2: Pattern Analysis
- Minimize reproduction — shrink to smallest scenario
- Find working examples in the same codebase
- Compare working vs broken, list every difference
- Understand dependencies and assumptions

#### Phase 3: Hypothesis & Testing
- Generate 3-5 falsifiable hypotheses, rank by likelihood
- Test one variable at a time
- Prefer REPL/breakpoint over logs
- Tag temporary logs with unique prefix for cleanup
### Phase 4: Implementation

- Create a failing test first (see TDD)
- One fix at a time, no "while I'm here" improvements
- If 3+ fixes failed → STOP and question the architecture

### Node.js Debugging (Tool Reference)

For Node.js/TypeScript debugging when `console.log` isn't enough, use `node inspect` or the Chrome DevTools Protocol (CDP) CLI. Full reference at `references/node-js-debugging.md`.

Quick patterns:

- **Launch paused:** `node --inspect-brk script.js` then `node inspect -p <pid>`
- **Attach to running process:** `kill -SIGUSR1 <pid>`, then `node inspect -p <pid>`
- **Vitest under debugger:** `node --inspect-brk ./node_modules/vitest/vitest.mjs run --no-file-parallelism test-file.tsx`
- **CDP scripting:** use `chrome-remote-interface` npm package for automated breakpoint/scope/callstack capture

Load the full reference when the user asks for Node debugging, breakpoint stepping, call-stack inspection, or heap/CPU profiling.

### Tight Loop Construction (Priority Order)
1. Failing test at the seam
2. HTTP script / curl against dev server
3. CLI invocation with fixture input
4. Headless browser script
5. Replay captured trace (HAR, event log)
6. Throwaway harness
7. Bisection harness for `git bisect run`
8. Differential loop (old vs new version)

### Subagent Support
```python
delegate_task(
    goal="Investigate why [test/behavior] fails",
    context="Report findings — do NOT fix yet. Follow systematic-debugging.",
    toolsets=['terminal', 'file']
)
```

---

## Section 3: Spike — Throwaway Experiments

Validate an idea before committing to a real build. Disposable by design.

### Core Loop
```
decompose → research → build → verdict
```

### Decompose
Break into 2-5 independent feasibility questions. Order by risk — the spike most likely to kill the idea runs first.

| # | Spike | Given/When/Then | Risk |
|---|-------|-----------------|------|
| 001 | websocket-streaming | Given WS, when LLM streams, then client receives <100ms chunks | High |

### Research (per spike)
- Brief it (2-3 sentences)
- Surface competing approaches
- Pick one, state why

### Build
- One directory per spike: `spikes/NNN-descriptive-name/`
- Bias toward something interactive (CLI, HTML page, server endpoint)
- Depth over speed — test edge cases, follow surprising findings

### Verdict
Each spike closes with:
```markdown
## Verdict: VALIDATED | PARTIAL | INVALIDATED
### What worked / What didn't / Surprises / Recommendation
```

### Comparison Spikes (002a / 002b)
Build back to back, then head-to-head:
```markdown
| Dimension | pdfjs (002a) | camelot (002b) |
|-----------|--------------|----------------|
| Quality | 9/10 | 7/10 |
| Setup | npm install | pip + ghostscript |
| Performance | 3s | 18s |

**Winner:** pdfjs for our use case.
```

---

## Section 4: Simplify Code — Parallel Cleanup

Review recent code changes with three focused reviewers running in parallel.

### When to Use
User says: "simplify", "review my code", "clean up my changes", "/simplify".

Custom modifiers: `focus on efficiency` (run only that reviewer), `don't change anything` (dry run), `last commit` / `staged` / `src/foo.py` (scope).

### Phase 1: Capture Diff
```bash
git diff                    # uncommitted
git diff HEAD               # include staged
git diff main...HEAD        # this branch
```

### Phase 2: Launch Three Reviewers (Parallel via delegate_task)

**Reviewer 1 — Code Reuse:** Search for duplicated functionality, existing utilities being reimplemented.

**Reviewer 2 — Code Quality:** Redundant state, parameter sprawl, copy-paste-with-variation, leaky abstractions, stringly-typed code, AI slop patterns.

**Reviewer 3 — Efficiency:** Unnecessary work, N+1 patterns, TOCTOU, memory leaks, silent failures, overly broad reads.

Each receives the **full diff**, searches the codebase, and reports with:
```
file:line → problem → fix | confidence: high/medium/low | risk: SAFE/CAREFUL/RISKY
```

### Phase 3: Aggregate & Apply
1. Merge, dedupe, discard false positives
2. Resolve conflicts: correctness > user's focus > readability > micro-perf
3. Apply: SAFE first (auto), CAREFUL next (verify), RISKY last (flag for human)

---

## Section 5: Pre-Commit Code Verification

Automated pipeline before code lands. **No agent should verify its own work** — fresh context finds what you miss.

---

## Section 6: Web QA Testing (Dogfooding)

Systematic exploratory QA testing of web applications using the browser toolset.

### When to Use

The user provides a target URL and asks you to test/find bugs/QA a web application. Works for any public or internal web app accessible via the browser tools.

### Workflow

#### Phase 1: Plan
1. Create output structure: `{output_dir}/screenshots/` and `{output_dir}/report.md`
2. Identify testing scope and build a rough sitemap (home page, navigation links, key user flows, forms, edge cases)

#### Phase 2: Explore
For each page or feature:
1. **Navigate** → `browser_navigate(url=...)`
2. **Snapshot** → `browser_snapshot()` to understand DOM
3. **Check console** → `browser_console(clear=true)` — silent JS errors are high-value finds
4. **Visual assessment** → `browser_vision(question="Describe layout, visual issues, accessibility concerns")`
5. **Test interactives** → click buttons, fill forms, test validation, scroll, keyboard navigation
6. **After each interaction** → re-check console for errors

#### Phase 3: Collect Evidence
For every issue found:
- Screenshot: `browser_vision(question="Capture the issue")`
- Record: URL, steps to reproduce, expected vs actual behavior, console errors
- Classify: severity (Critical/High/Medium/Low) and category (Functional/Visual/Accessibility/UX/Console/Content)

#### Phase 4: Categorize
De-duplicate, assign final severity, sort by severity, count by severity/category.

#### Phase 5: Report
Generate report with: executive summary, per-issue sections (title, severity, category, URL, steps, expected vs actual, screenshots), summary table, testing notes.

### Issue Categories
| Category | Examples |
|----------|----------|
| **Functional** | Broken links, form submission fails, button does nothing, API errors |
| **Visual** | Layout breakage, overlapping elements, missing images, responsive issues |
| **Accessibility** | Missing labels, keyboard traps, low contrast, missing ARIA attributes |
| **Console** | JS errors, uncaught exceptions, deprecation warnings |
| **UX** | Poor flow, confusing navigation, unclear feedback, slow interactions |
| **Content** | Typos, outdated info, broken references, placeholder text left in |

### Tips
- Always check `browser_console()` after navigating and after significant interactions
- Use `annotate=true` with `browser_vision` when you need element position labels
- Test with both valid and invalid inputs — form validation bugs are common
- Scroll through long pages — content below the fold may have rendering issues
- Don't forget edge cases: empty states, very long text, special characters, rapid clicking

### Step 1: Get the diff
```bash
git diff --cached        # staged
git diff                 # unstaged
git diff HEAD~1          # last commit
```

### Step 2: Static Security Scan (Added Lines Only)
```bash
git diff --cached | grep "^+" | grep -iE "(api_key|secret|password|token)\s*=\s*['\"][^'\"]{6,}['\"]"
git diff --cached | grep "^+" | grep -E "os\.system\(|subprocess.*shell=True|eval\(|exec\("
```

### Step 3: Baseline Tests & Linting
Detect framework, run baseline (stash, run, pop), compare: **only NEW failures block commit**.

### Step 4: Self-Review Checklist
- No hardcoded secrets, input validation, parameterized queries, error handling
- No debug prints / console.log left behind
- New code has tests

### Step 5: Independent Reviewer Subagent
```python
delegate_task(
    goal="""Review git diff. Return ONLY JSON:
{"passed": bool, "security_concerns": [...], "logic_errors": [...], "suggestions": [...], "summary": "..."}
FAIL-CLOSED: security_concerns or logic_errors non-empty → passed=false""",
    context="Independent code review. Return only JSON.",
    toolsets=["terminal"]
)
```

### Step 6-7: Auto-Fix Loop (max 2 cycles)
Spawn a fix agent focused ONLY on reported issues. Re-verify after each cycle. Escalate to user after 2 failures.

### Step 8: Commit
```bash
git add -A && git commit -m "[verified] <description>"
```

---

## Section 7: Project-Portable Agent Setup

When setting up a project that needs its own isolated Hermes Agent configuration (skills, memory, sessions) with full portability — copy the entire project folder, agent config goes with it.

**Pattern:** place a dedicated `.hermes/` directory inside the project folder, launch with `HERMES_HOME` pointing to it.

Load the reference for exact steps, migration guide, and CLI/desktop launch scripts:

```
skill_view(name="development-methodology", file_path="references/project-portable-agent-setup.md")
```

This applies when the user says "I want to copy the whole project folder to another machine" or "don't mix my project config with my system Hermes."

---

## Combined Workflow

For a full feature implementation cycle:
1. **Spike** if needed to validate approach
2. **TDD** for each behavior: RED→GREEN→REFACTOR
3. **Simplify** after implementation to clean up
4. **Pre-commit review** before push
5. **Systematic debugging** if tests fail or bugs surface

## Subagent Delegation Patterns

All processes support subagent delegation for parallel or isolated work:

```python
# TDD subagent
delegate_task(goal="Implement feature with strict TDD", ...)

# Debugging subagent
delegate_task(goal="Investigate root cause of test failure", ...)

# Simplify subagent (3 reviewers in batch mode)
delegate_task(tasks=[reuse_reviewer, quality_reviewer, efficiency_reviewer])

# Pre-commit reviewer
delegate_task(goal="Review diff for security issues and logic errors", ...)
```
