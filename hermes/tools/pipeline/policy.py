"""V3 deterministic Policy/Guard adapters.

The V3 Coordinator keeps safety deterministic.  This module reuses the existing
Warden quality checks rather than duplicating their parameter rules, and accepts
an explicit system-health snapshot from the submit adapter.
"""

from __future__ import annotations

from typing import Any, Mapping


def _config_identity(config: Mapping[str, Any]) -> tuple[str, int, int, str, float]:
    ratios = str(config.get("ratios", "")).replace(" ", "")
    return (
        str(config.get("slot", "")),
        int(config.get("sd", 0)),
        int(config.get("sc", 0)),
        ratios,
        float(config.get("of", 0.0)),
    )


def verify_system_health(snapshot: Mapping[str, Any] | None) -> tuple[bool, str]:
    """Verify an authenticated asset/DB health snapshot before a Unity run.

    A caller may omit a snapshot during fixture-free unit operations. When one
    is provided it must be internally consistent; a self-declared ``reason`` is
    never trusted without comparing the actual configurations.
    """

    if snapshot is None:
        return True, ""
    if not isinstance(snapshot, Mapping):
        return False, "system_health_invalid"
    asset = snapshot.get("asset_configs")
    database = snapshot.get("database_configs")
    if not isinstance(asset, list) or not isinstance(database, list):
        return False, "system_health_invalid"
    try:
        asset_by_slot = {str(item["slot"]): _config_identity(item) for item in asset}
        db_by_slot = {str(item["slot"]): _config_identity(item) for item in database}
    except (KeyError, TypeError, ValueError):
        return False, "system_health_invalid"
    if set(asset_by_slot) != set(db_by_slot):
        return False, "asset_db_fingerprint_mismatch"
    for slot, asset_config in asset_by_slot.items():
        if asset_config != db_by_slot[slot]:
            return False, "asset_db_fingerprint_mismatch"
    return True, ""


def _probe_quality_guard(request: Mapping[str, Any]) -> tuple[bool, str]:
    """Run the existing W02/W09 pure checks over V3 probe maps."""

    probes = request.get("probes", {})
    if not isinstance(probes, Mapping):
        return False, "W02 probes_missing"
    requested_levels = {str(level) for level in request.get("levels", [])}
    provided_levels = {str(level) for level in probes}
    if requested_levels != provided_levels:
        missing = sorted(requested_levels - provided_levels)
        extra = sorted(provided_levels - requested_levels)
        return False, f"W02 probe_level_coverage_mismatch missing={missing} extra={extra}"
    try:
        from tools.warden import check_5_slots, check_probe_quality
    except Exception as exc:
        return False, f"W09 guard_import_failed:{exc}"
    for level, tiers in probes.items():
        ok, detail = check_5_slots(tiers)
        if not ok:
            return False, f"W02 L{level} {detail}"
        ok, detail = check_probe_quality(tiers)
        if not ok:
            return False, f"W09 L{level} {detail}"
    return True, ""


def _health_guard(request: Mapping[str, Any]) -> tuple[bool, str]:
    ok, detail = verify_system_health(request.get("system_health"))
    return ok, detail


def production_guards():
    """Return the deterministic pre-run guard list used by V3 Coordinator."""

    return [_probe_quality_guard, _health_guard]


class PolicyEvaluator:
    """Reserved P0.4 policy seam; judgment logic is attached in the policy slice."""

    @staticmethod
    def evaluate(snapshot: Mapping[str, Any]):
        raise NotImplementedError("PolicyEvaluator.evaluate is implemented with P0.4 judgment slice")
