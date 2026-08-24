"""Shared contract diagnostics for the V3 pipeline skeleton."""

from __future__ import annotations


class ContractNotImplemented(NotImplementedError):
    """Raised while a declared public V3 seam has no behavior yet."""

    def __init__(self, contract_id: str):
        self.contract_id = contract_id
        super().__init__(f"V3 contract not implemented: {contract_id}")
