# Unity Version Mismatch: Batch Mode Package Resolution Failure

**Date:** 2026-07-29
**Impact:** Batch mode failed for hours with misleading "error resolving packages" message.

## Root Cause

`submit_batch_unity.py` hardcoded `UNITY_EXE` to `2022.3.62f2` but the project's `ProjectSettings/ProjectVersion.txt` was `6000.0.60f1`.

Unity 2022.3 ships with `com.unity.ugui` 1.0.0 as built-in. Unity 6000 ships with 2.0.0. The project's `BettaFramework` and `BettaInterface` local packages require ugui 2.0.0.

In batch mode, Unity cannot download packages from the registry (no network). It can only use cached packages and built-ins. 2022.3's built-in ugui 1.0.0 fails the 2.0.0 dependency.

## Misleading Error

```
[Licensing::Client] Error: HandshakeResponse reported an error:
An error occurred while resolving packages:
Unity exited with code 1
```

The license error is a red herring (non-fatal). The real error is hidden in the raw Unity output:

```
Package com.betta.unity.framework requires com.unity.ugui 2.0.0 but resolved 1.0.0
```

## Failed Diagnosis Attempts

- Deleted and restored `.asset.meta` files — unrelated
- Deleted `PackageCache` — made it worse (cache wiped, batch mode can't re-download)
- Deleted `packages-lock.json` — regenerated with same conflict
- Attempted to force ugui version in lock file — overwritten by batch mode resoluion
- Opened Unity in GUI mode to download 2.0.0 — killed by `taskkill` before cache persisted

## Correct Diagnosis

1. Run Unity directly: `Unity.exe -batchmode -quit -projectPath . -logFile -`
2. Found: `com.unity.ugui 1.0.0 does not satisfy 2.0.0`
3. Checked `ProjectSettings/ProjectVersion.txt`: `6000.0.60f1`
4. Checked `submit_batch_unity.py` UNITY_EXE: `2022.3.62f2`
5. **Fix:** Change UNITY_EXE to `6000.0.60f1`

## Verification

- Unity 6000 ships with ugui 2.0.0 built-in → no download needed
- Batch mode resolved all packages immediately
- License warning persists but is non-fatal

## Lessons

1. When batch mode fails with "resolving packages", check `ProjectVersion.txt` against the UNITY_EXE path FIRST
2. The license `HandshakeResponse` error is a non-fatal warning — don't fixate on it
3. Don't delete PackageCache, .meta, or Library to "fix" package resolution — these are secondary symptoms
4. Use `delegate_task` with a fresh subagent for stubborn diagnosis — it found the root cause when the main agent was stuck
