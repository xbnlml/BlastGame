#!/usr/bin/env python3
"""Public batch-receipt contracts from real shared-CSV incidents."""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2]
FIXTURES = HERMES / "tests" / "fixtures"
sys.path.insert(0, str(HERMES))


@contextmanager
def copied_fixture(name: str):
    """Give each mutation test an isolated copy; never modify checked-in evidence."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / name
        shutil.copytree(FIXTURES / name, target)
        yield target


def load_request(root: Path) -> dict:
    return json.loads((root / "request.json").read_text(encoding="utf-8"))


def pairs(rows: list[dict] | list[list[str]]) -> set[tuple[str, str]]:
    if rows and isinstance(rows[0], dict):
        return {(str(row["level"]), str(row["slot"])) for row in rows}
    return {(str(level), str(slot)) for level, slot in rows}


def artifact_identity(row: dict) -> tuple[str, str, int, str, str]:
    return (
        str(row["level"]), str(row["slot"]), int(row["tier"]),
        str(row["board_fingerprint"]), str(row["deal_fingerprint"]),
    )


def mutate_csv(path: Path, mutate) -> None:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys())
    mutate(rows)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class BatchReceiptContractTest(unittest.TestCase):
    """`verify_batch_artifacts(bot_root, request)` is the public artifact seam."""

    def test_exact_batch_accepts_all_35_fingerprinted_rows(self):
        from tools.pipeline.batch_run import verify_batch_artifacts

        with copied_fixture("shared_csv_7_levels") as fixture:
            request = load_request(fixture)
            receipt = verify_batch_artifacts(
                fixture / "telemetry" / "bot", request
            )

        self.assertEqual("accepted", receipt["status"])
        self.assertEqual(
            {
                key: request[key]
                for key in (
                    "run_id", "attempt_id", "batch_id", "request_plan_hash",
                    "executed_plan_hash", "logic_version",
                )
            },
            receipt["identity"],
        )
        expected = {
            (
                row["level"], row["slot"], row["tier"],
                row["board_fingerprint"], row["deal_fingerprint"],
            )
            for row in request["expected_artifacts"]
        }
        observed = {
            (
                row["level"], row["slot"], row["tier"],
                row["board_fingerprint"], row["deal_fingerprint"],
            )
            for row in receipt["artifacts"]
        }
        self.assertEqual(35, len(observed))
        self.assertEqual(expected, observed)
        sentinel = next(
            row for row in receipt["artifacts"]
            if row["level"] == "60" and row["slot"] == "T1"
        )
        self.assertEqual(0.875, sentinel["win_rate"])
        self.assertEqual(
            "ee8d47b49c88db271e834fb10ac33e51d92d7b4454401f21e80e2c57986a9182",
            sentinel["deal_fingerprint"],
        )
        self.assertEqual([], receipt["missing_pairs"])

    def test_requested_batch_identity_wins_over_newer_unrelated_directory(self):
        from tools.pipeline.batch_run import verify_batch_artifacts

        with copied_fixture("stale_latest_dir") as fixture:
            request = load_request(fixture)
            bot_root = fixture / "telemetry" / "bot"
            requested = bot_root / request["batch_id"]
            unrelated = bot_root / "batch-unrelated-newer"
            os.utime(requested, (1, 1))
            os.utime(unrelated, (2, 2))
            receipt = verify_batch_artifacts(bot_root, request)

        self.assertEqual("accepted", receipt["status"])
        self.assertEqual("batch-requested", receipt["identity"]["batch_id"])
        self.assertEqual({("60", "T1")}, pairs(receipt["artifacts"]))

    def test_partial_receipt_preserves_success_and_retries_only_missing_pairs(self):
        from tools.pipeline.batch_run import verify_batch_artifacts

        with copied_fixture("partial_batch") as fixture:
            request = load_request(fixture)
            receipt = verify_batch_artifacts(
                fixture / "telemetry" / "bot", request
            )

        self.assertEqual("partial", receipt["status"])
        expected_accepted = {
            artifact_identity(row) for row in request["expected_artifacts"]
            if (row["level"], row["slot"]) == ("60", "T1")
        }
        self.assertEqual(expected_accepted, {artifact_identity(row) for row in receipt["accepted_artifacts"]})
        missing = {("60", "T2"), ("62", "T1"), ("62", "T2")}
        self.assertEqual(missing, pairs(receipt["missing_pairs"]))
        self.assertEqual(missing, pairs(receipt["retry_pairs"]))
        self.assertEqual(request["attempt_id"], receipt["identity"]["attempt_id"])

    def test_partial_receipt_or_csv_artifact_identity_is_rejected_when_tampered(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        cases = (
            ("receipt-level", "RECEIPT_ARTIFACT_MISMATCH"),
            ("csv-tier", "CSV_ARTIFACT_MISMATCH"),
        )
        for mutation, expected_code in cases:
            with self.subTest(mutation=mutation):
                with copied_fixture("partial_batch") as fixture:
                    request = load_request(fixture)
                    bot_root = fixture / "telemetry" / "bot"
                    if mutation == "receipt-level":
                        receipt_path = next(bot_root.rglob("unity_receipt.json"))
                        raw = json.loads(receipt_path.read_text(encoding="utf-8"))
                        raw["artifacts"][0]["level"] = "62"
                        receipt_path.write_text(json.dumps(raw), encoding="utf-8")
                    else:
                        csv_path = next(bot_root.rglob("campaign-summary-*.csv"))
                        mutate_csv(csv_path, lambda rows: rows.__setitem__(0, {**rows[0], "Tier": "2"}))
                    with self.assertRaises(ArtifactVerificationError) as caught:
                        verify_batch_artifacts(bot_root, request)

                self.assertEqual(expected_code, caught.exception.code)

    def test_receipt_rejects_plan_hash_inequality_even_when_request_and_receipt_agree(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        with copied_fixture("shared_csv_7_levels") as fixture:
            request = load_request(fixture)
            request["executed_plan_hash"] = "a" * 64
            receipt_path = next((fixture / "telemetry" / "bot").rglob("unity_receipt.json"))
            raw = json.loads(receipt_path.read_text(encoding="utf-8"))
            raw["executed_plan_hash"] = "a" * 64
            receipt_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ArtifactVerificationError) as caught:
                verify_batch_artifacts(fixture / "telemetry" / "bot", request)

        self.assertEqual("PLAN_HASH_MISMATCH", caught.exception.code)

    def test_duplicate_csv_row_is_rejected_before_ingest(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        with copied_fixture("shared_csv_7_levels") as fixture:
            request = load_request(fixture)
            path = next((fixture / "telemetry" / "bot").rglob("campaign-summary-T1.csv"))
            mutate_csv(path, lambda rows: rows.append(dict(rows[0])))
            with self.assertRaises(ArtifactVerificationError) as caught:
                verify_batch_artifacts(fixture / "telemetry" / "bot", request)

        self.assertEqual("DUPLICATE_ARTIFACT", caught.exception.code)

    def test_wrong_csv_deal_fingerprint_is_rejected_before_ingest(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        with copied_fixture("shared_csv_7_levels") as fixture:
            request = load_request(fixture)
            path = next((fixture / "telemetry" / "bot").rglob("campaign-summary-T1.csv"))
            mutate_csv(path, lambda rows: rows.__setitem__(1, {**rows[1], "DealFingerprint": "f" * 64}))
            with self.assertRaises(ArtifactVerificationError) as caught:
                verify_batch_artifacts(fixture / "telemetry" / "bot", request)

        self.assertEqual("CSV_ARTIFACT_MISMATCH", caught.exception.code)

    def test_wrong_csv_board_fingerprint_or_numeric_tier_is_rejected_before_ingest(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        for field, value in (("BoardFingerprint", "a" * 64), ("Tier", "5")):
            with self.subTest(field=field):
                with copied_fixture("shared_csv_7_levels") as fixture:
                    request = load_request(fixture)
                    path = next((fixture / "telemetry" / "bot").rglob("campaign-summary-T1.csv"))
                    mutate_csv(path, lambda rows: rows.__setitem__(1, {**rows[1], field: value}))
                    with self.assertRaises(ArtifactVerificationError) as caught:
                        verify_batch_artifacts(fixture / "telemetry" / "bot", request)

                self.assertEqual("CSV_ARTIFACT_MISMATCH", caught.exception.code)

    def test_extra_unrequested_csv_row_is_rejected(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        with copied_fixture("shared_csv_7_levels") as fixture:
            request = load_request(fixture)
            path = next((fixture / "telemetry" / "bot").rglob("campaign-summary-T1.csv"))
            def add_extra(rows):
                rows.append({
                    **rows[0], "level": "999", "BoardFingerprint": "e" * 64,
                    "V2BoardFingerprint": "e" * 64, "DealFingerprint": "d" * 64,
                })
            mutate_csv(path, add_extra)
            with self.assertRaises(ArtifactVerificationError) as caught:
                verify_batch_artifacts(fixture / "telemetry" / "bot", request)

        self.assertEqual("UNREQUESTED_ARTIFACT", caught.exception.code)

    def test_each_receipt_identity_field_is_rejected_when_tampered(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        for field, value in (
            ("run_id", "wrong-run"),
            ("attempt_id", "wrong-attempt"),
            ("batch_id", "wrong-batch"),
            ("request_plan_hash", "a" * 64),
            ("executed_plan_hash", "b" * 64),
            ("logic_version", "old-logic-version"),
        ):
            with self.subTest(field=field):
                with copied_fixture("shared_csv_7_levels") as fixture:
                    request = load_request(fixture)
                    receipt_path = next((fixture / "telemetry" / "bot").rglob("unity_receipt.json"))
                    raw = json.loads(receipt_path.read_text(encoding="utf-8"))
                    raw[field] = value
                    receipt_path.write_text(json.dumps(raw), encoding="utf-8")
                    with self.assertRaises(ArtifactVerificationError) as caught:
                        verify_batch_artifacts(fixture / "telemetry" / "bot", request)

                self.assertEqual("RECEIPT_IDENTITY_MISMATCH", caught.exception.code)

    def test_receipt_artifact_identity_is_rejected_when_tampered(self):
        from tools.pipeline.batch_run import ArtifactVerificationError, verify_batch_artifacts

        for field, value in (
            ("board_fingerprint", "a" * 64),
            ("deal_fingerprint", "b" * 64),
            ("tier", 5),
        ):
            with self.subTest(field=field):
                with copied_fixture("shared_csv_7_levels") as fixture:
                    request = load_request(fixture)
                    receipt_path = next((fixture / "telemetry" / "bot").rglob("unity_receipt.json"))
                    raw = json.loads(receipt_path.read_text(encoding="utf-8"))
                    raw["artifacts"][0][field] = value
                    receipt_path.write_text(json.dumps(raw), encoding="utf-8")
                    with self.assertRaises(ArtifactVerificationError) as caught:
                        verify_batch_artifacts(fixture / "telemetry" / "bot", request)

                self.assertEqual("RECEIPT_ARTIFACT_MISMATCH", caught.exception.code)


if __name__ == "__main__":
    unittest.main(verbosity=2)