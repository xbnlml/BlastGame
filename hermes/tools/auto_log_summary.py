#!/usr/bin/env python3
"""Shared parsers for auto_loop's human-readable log protocol."""
from __future__ import annotations

import re


_SUMMARY_PATTERNS = {
    "passed": r"Passed \(待确认入库\):\s*(\d+)\s+levels",
    "failed": r"Failed \(改关卡\):\s*(\d+)\s+levels",
    "errors": r"Errors:\s*(\d+)\s+levels",
}


def parse_final_summary(log_text: str) -> dict[str, int] | None:
    """Parse a complete FINAL SUMMARY, or return None when incomplete."""
    values: dict[str, int] = {}
    for name, pattern in _SUMMARY_PATTERNS.items():
        match = re.search(pattern, log_text)
        if match is None:
            return None
        values[name] = int(match.group(1))
    return values


def phase_sequences(log_text: str) -> list[list[int]]:
    """Return phase numbers grouped by round.

    A repeated Phase 1 starts a new round even when a historical log lacks an
    explicit ROUND heading. Repeated adjacent phase labels are collapsed so
    wrapped/duplicated log output does not create a false violation.
    """
    sequences: list[list[int]] = []
    current: list[int] = []
    for line in log_text.splitlines():
        match = re.search(r"\bPhase\s+(\d+)\b", line)
        if match is None:
            continue
        phase = int(match.group(1))
        if phase == 1 and current:
            sequences.append(current)
            current = []
        if not current or current[-1] != phase:
            current.append(phase)
    if current:
        sequences.append(current)
    return sequences


def invalid_phase_sequences(log_text: str) -> list[list[int]]:
    """Return rounds whose observed phases move backwards or start after 1."""
    invalid = []
    for sequence in phase_sequences(log_text):
        if not sequence or sequence[0] != 1:
            invalid.append(sequence)
            continue
        if any(current <= previous for previous, current in zip(sequence, sequence[1:])):
            invalid.append(sequence)
    return invalid
