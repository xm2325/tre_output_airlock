from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from clinical_genomic_pipeline.contracts import evaluate_contract
from clinical_genomic_pipeline.fhir import transform_bundle, validate_bundle
from clinical_genomic_pipeline.hashing import pseudonymise
from clinical_genomic_pipeline.operations import build_operations_summary, render_operations_html
from clinical_genomic_pipeline.pipeline import run_pipeline
from clinical_genomic_pipeline.storage import (
    build_curated_publish_plan,
    upload_curated_publish_plan,
)
from clinical_genomic_pipeline.terminology import (
    build_terminology_report,
    load_terminology_map,
)
from clinical_genomic_pipeline.transfer import (
    build_transfer_receipt,
    validate_transfer_receipt,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class ClinicalGenomicPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]
        self.fhir = self.root / "samples" / "fhir_bundle.json"
        self.manifest = self.root / "samples" / "genomic_manifest.csv"
        self.vcf = self.root / "samples" / "genomics" / "sample_001.vcf"
        self.terminology_map = self.root / "reference" / "terminology_map.csv"
        self.secret = "test-secret-at-least-16-characters"

    def _copy_delivery(self, directory: Path) -> tuple[Path, Path, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        fhir = directory / "fhir_bundle.json"
        manifest = directory / "genomic_manifest.csv"
        receipt = directory / "transfer_receipt.json"
        genomics = directory / "genomics"
        genomics.mkdir()
        shutil.copy2(self.fhir, fhir)
        shutil.copy2(self.manifest, manifest)
        shutil.copy2(self.vcf, genomics / "sample_001.vcf")
        self._rebuild_receipt(directory, receipt)
        return fhir, manifest, receipt

    def _rebuild_receipt(self, directory: Path, receipt: Path) -> None:
        build_transfer_receipt(
            delivery_root=directory,
            relative_paths=[
                "fhir_bundle.json",
                "genomic_manifest.csv",
                "genomics/sample_001.vcf",
            ],
            output_path=receipt,
            tool="GLOBUS",
            transfer_id="globus-test-001",
            source_endpoint="nhs-source-demo",
            destination_endpoint="landing-zone-demo",
        )

    def _run_valid_delivery(self, root: Path) -> Any:
        fhir, manifest, receipt = self._copy_delivery(root / "delivery")
        return run_pipeline(
            fhir_path=fhir,
            genomic_manifest_path=manifest,
            transfer_receipt_path=receipt,
            terminology_map_path=self.terminology_map,
            output_root=root / "output",
            secret=self.secret,
        )

    def test_pseudonymisation_is_stable_and_secret_dependent(self) -> None:
        first = pseudonymise("patient-001", self.secret)
        second = pseudonymise("patient-001", self.secret)
        different = pseudonymise("patient-001", "another-secret-at-least-16")
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertNotIn("patient-001", first)

    def test_fhir_transform_removes_direct_identifiers(self) -> None:
        bundle = json.loads(self.fhir.read_text(encoding="utf-8"))
        self.assertEqual(validate_bundle(bundle), [])
        output = transform_bundle(bundle, self.secret)
        serialised = json.dumps(output.people)
        self.assertNotIn("Synthetic", serialised)
        self.assertNotIn("Exampletown", serialised)
        self.assertNotIn("ZZ1 1ZZ", serialised)
        self.assertEqual(len(output.people), 1)
        self.assertEqual(len(output.conditions), 1)
        self.assertEqual(len(output.measurements), 1)

    def test_contract_fingerprint_is_stable(self) -> None:
        bundle = json.loads(self.fhir.read_text(encoding="utf-8"))
        first = evaluate_contract(bundle, self.manifest)
        second = evaluate_contract(bundle, self.manifest)
        self.assertEqual(first["status"], "PASS")
        self.assertEqual(first["schema_fingerprint"], second["schema_fingerprint"])

    def test_transfer_receipt_checks_files_bytes_and_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fhir, manifest, receipt = self._copy_delivery(root)
            rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
            genomic_file = (root / rows[0]["vcf_path"]).resolve()
            report, issues = validate_transfer_receipt(
                receipt_path=receipt,
                delivery_root=root,
                expected_files=[fhir, manifest, genomic_file],
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["tool"], "GLOBUS")
            self.assertEqual(issues, [])

            genomic_file.write_text(genomic_file.read_text() + "#tampered\n", encoding="utf-8")
            failed_report, failed_issues = validate_transfer_receipt(
                receipt_path=receipt,
                delivery_root=root,
                expected_files=[fhir, manifest, genomic_file],
            )
            self.assertEqual(failed_report["status"], "FAIL")
            self.assertIn("TRANSFER_CHECKSUM_MISMATCH", {issue.code for issue in failed_issues})

    def test_pipeline_writes_omop_transfer_quality_and_reuses_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._run_valid_delivery(root)
            self.assertFalse(first.reused_existing_run)
            self.assertEqual(first.warning_count, 0)
            self.assertTrue((first.run_directory / "_SUCCESS").is_file())
            self.assertTrue((first.run_directory / "transfer_report.json").is_file())
            self.assertTrue((first.run_directory / "data_quality_report.json").is_file())
            self.assertTrue(
                (first.run_directory / "gold" / "omop" / "person.csv").is_file()
            )
            self.assertTrue(
                (first.run_directory / "gold" / "omop" / "measurement.csv").is_file()
            )
            condition_text = (
                first.run_directory / "gold" / "omop" / "condition_occurrence.csv"
            ).read_text(encoding="utf-8")
            measurement_text = (
                first.run_directory / "gold" / "omop" / "measurement.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("201826", condition_text)
            self.assertIn("3004410", measurement_text)

            research_text = "\n".join(
                path.read_text(encoding="utf-8")
                for zone in ("silver", "gold")
                for path in (first.run_directory / zone).rglob("*")
                if path.is_file()
            )
            for direct_identifier in (
                "patient-001",
                "specimen-001",
                "sample-001",
                "Synthetic",
                "Exampletown",
                "ZZ1 1ZZ",
            ):
                self.assertNotIn(direct_identifier, research_text)

            fhir = root / "delivery" / "fhir_bundle.json"
            manifest = root / "delivery" / "genomic_manifest.csv"
            receipt = root / "delivery" / "transfer_receipt.json"
            second = run_pipeline(
                fhir_path=fhir,
                genomic_manifest_path=manifest,
                transfer_receipt_path=receipt,
                terminology_map_path=self.terminology_map,
                output_root=root / "output",
                secret=self.secret,
            )
            self.assertTrue(second.reused_existing_run)
            self.assertEqual(first.run_id, second.run_id)

    def test_additive_contract_drift_warns_but_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            delivery = root / "delivery"
            fhir, manifest, receipt = self._copy_delivery(delivery)
            bundle = json.loads(fhir.read_text(encoding="utf-8"))
            bundle["entry"][0]["resource"]["researchTag"] = "new-source-field"
            fhir.write_text(json.dumps(bundle), encoding="utf-8")
            self._rebuild_receipt(delivery, receipt)

            result = run_pipeline(
                fhir_path=fhir,
                genomic_manifest_path=manifest,
                transfer_receipt_path=receipt,
                terminology_map_path=self.terminology_map,
                output_root=root / "output",
                secret=self.secret,
            )
            report = json.loads(
                (result.run_directory / "contract_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result.warning_count, 1)
            self.assertEqual(report["status"], "WARN")
            self.assertEqual(report["drift"][0]["field"], "researchTag")

    def test_breaking_manifest_drift_is_quarantined_before_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fhir, manifest, receipt = self._copy_delivery(root / "delivery")
            rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
            fieldnames = [
                "sample_id",
                "patient_reference",
                "specimen_reference",
                "vcf_path",
                "expected_sha256",
            ]
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

            output = root / "output"
            with self.assertRaisesRegex(ValueError, "breaking contract"):
                run_pipeline(
                    fhir_path=fhir,
                    genomic_manifest_path=manifest,
                    transfer_receipt_path=receipt,
                    terminology_map_path=self.terminology_map,
                    output_root=output,
                    secret=self.secret,
                )
            quarantine = next((output / "quarantine").iterdir())
            report = json.loads(
                (quarantine / "contract_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "FAIL")

    def test_checksum_mismatch_is_quarantined_after_valid_transfer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            delivery = root / "delivery"
            fhir, manifest, receipt = self._copy_delivery(delivery)
            rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
            rows[0]["expected_sha256"] = "0" * 64
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            self._rebuild_receipt(delivery, receipt)

            output = root / "output"
            with self.assertRaisesRegex(ValueError, "quarantined"):
                run_pipeline(
                    fhir_path=fhir,
                    genomic_manifest_path=manifest,
                    transfer_receipt_path=receipt,
                    terminology_map_path=self.terminology_map,
                    output_root=output,
                    secret=self.secret,
                )
            issue_files = list((output / "quarantine").glob("*/validation_issues.json"))
            issues = json.loads(issue_files[0].read_text(encoding="utf-8"))
            self.assertEqual(issues[0]["code"], "GENOMIC_CHECKSUM_MISMATCH")

    def test_unknown_terminology_is_reported_for_review(self) -> None:
        bundle = json.loads(self.fhir.read_text(encoding="utf-8"))
        clinical = transform_bundle(bundle, self.secret)
        clinical.measurements[0]["source_code"] = "unknown-code"
        mapping = load_terminology_map(self.terminology_map)
        report = build_terminology_report(
            clinical.conditions,
            clinical.measurements,
            mapping,
        )
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["review_required_count"], 1)
        self.assertEqual(report["mapping_coverage"], 0.5)

    def test_s3_curated_plan_excludes_restricted_and_uses_kms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run_valid_delivery(Path(temporary))
            plan = build_curated_publish_plan(
                run_directory=result.run_directory,
                bucket="synthetic-curated-bucket",
                prefix="clinical-genomic",
            )
            source_paths = [str(item["source_path"]) for item in plan]
            self.assertTrue(any("gold/omop/person.csv" in path for path in source_paths))
            self.assertFalse(any("restricted" in path for path in source_paths))
            self.assertFalse(any("bronze" in path for path in source_paths))

            client = FakeS3Client()
            report = upload_curated_publish_plan(
                plan=plan,
                client=client,
                kms_key_id="alias/synthetic-clinical-genomic",
            )
            self.assertEqual(report["object_count"], len(plan))
            self.assertTrue(client.calls)
            self.assertTrue(
                all(call["ServerSideEncryption"] == "aws:kms" for call in client.calls)
            )

    def test_operations_summary_includes_transfer_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._run_valid_delivery(root)
            output = root / "output"
            summary = build_operations_summary(output)
            dashboard = render_operations_html(summary)
            self.assertEqual(summary["successful_count"], 1)
            self.assertEqual(summary["quarantined_count"], 0)
            self.assertEqual(summary["status"], "HEALTHY")
            self.assertEqual(summary["runs"][0]["transfer_tool"], "GLOBUS")
            self.assertEqual(summary["runs"][0]["data_quality_status"], "PASS")
            self.assertEqual(summary["runs"][0]["terminology_mapping_coverage"], 1.0)
            self.assertIn("Clinical–Genomic Pipeline Operations", dashboard)


if __name__ == "__main__":
    unittest.main()
