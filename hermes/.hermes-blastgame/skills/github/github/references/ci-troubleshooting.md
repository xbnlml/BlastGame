# CI Troubleshooting Quick Reference

Common CI failure patterns and how to diagnose them.

## Reading CI Logs
```bash
gh run view <RUN_ID> --log-failed
# Or curl:
curl -sL -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$GH_OWNER/$GH_REPO/actions/runs/<RUN_ID>/logs \
  -o /tmp/ci-logs.zip && unzip -o /tmp/ci-logs.zip -d /tmp/ci-logs
```

## Common Failure Patterns

**Test failures:** assertion errors, ModuleNotFoundError
→ Update assertion or add missing dependency

**Lint/formatting:** style violations
→ Run formatter: `black .`, `ruff check --fix .`

**Type check (mypy/pyright):** type mismatches
→ Fix function signature or add type cast

**Build failures:** missing deps, version conflicts
→ Add to requirements.txt / package.json

**Permission/auth:** token scope issues
→ Add `permissions:` block to workflow YAML

**Timeouts:** hung processes, slow network
→ Add `timeout-minutes: N` to the step

## Auto-Fix Decision Tree
```
CI Failed
├── Test failure → update test or fix logic
├── Lint failure → run formatter
├── Type error → fix types
├── Build failure → add/update dependency
├── Permission error → update workflow permissions
└── Timeout → investigate perf
```
