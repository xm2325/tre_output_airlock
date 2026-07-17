from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from clinical_genomic_pipeline.contracts import evaluate_contract
from clinical_genomic_pipeline.fhir import transform_bundle, validate_bundle
from clinical_genomic_pipeline.hashing import pseudonymise
from clinical_genomic_pipeline.operations import build_operations_summary, render_operations_html
from clinical_genomic_pipeline.pipeline import run_pipeline


class ClinicalGenomicPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]
        self.fhir = self.root / "samples" / "fhir_bundle.json"
        self.manifest = self.root / "samples" / "genomic_manifest.csv"
        self.vcf = self.root / "samples" / "genomics" / "sample_001.vcf"
        self.secret = "test-secret-at-least-16-characters"

    def _copy_delivery(self, directory: Path) -> tuple[Path, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        fhir = directory / "fhir_bundle.json"
        manifest = directory / "genomic_manifest.csv"
        genomics = directory / "genomics"
        genomics.mkdir()
        shutil.copy2(self.fhir, fhir)
        shutil.copy2(self.manifest, manifest)
        shutil.copy2(self.vcf, genomics / "sample_001.vcf")
        return fhir, manifest

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

    def test_pipeline_writes_layers_lineage_and_reuses_successful_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = run_pipeline(
                fhir_path=self.fhir,
                genomic_manifest_path=self.manifest,
                output_root=output,
                secret=self.secret,
            )
            self.assertFalse(first.reused_existing_run)
            self.assertEqual(first.warning_count, 0)
            self.assertTrue((first.run_directory / "_SUCCESS").is_file())
            self.assertTrue((first.run_directory / "lineage.json").is_file())
            self.assertTrue((first.run_directory / "contract_report.json").is_file())
            self.assertTrue((first.run_directory / "gold" / "research_cohort.csv").is_file())
            self.assertTrue(
                (first.run_directory / "restricted" / "patient_linkage.csv").is_file()
            )
            self.assertTrue(
                (first.run_directory / "restricted" / "specimen_linkage.csv").is_file()
            )

            research_text = "\n".join(
                path.read_text(encoding="utf-8")
                for zone in ("silver", "gold")
                for path in (first.run_directory / zone).glob("*")
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

            second = run_pipeline(
                fhir_path=self.fhir,
                genomic_manifest_path=self.manifest,
                output_root=output,
                secret=self.secret,
            )
            self.assertTrue(second.reused_existing_run)
            self.assertEqual(first.run_id, second.run_id)

    def test_additive_contract_drift_warns_but_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fhir, manifest = self._copy_delivery(root / "delivery")
            bundle = json.loads(fhir.read_text(encoding="utf-8"))
            bundle["entry"][0]["resource"]["researchTag"] = "new-source-field"
            fhir.write_text(json.dumps(bundle), encoding="utf-8")

            result = run_pipeline(
                fhir_path=fhir,
                genomic_manifest_path=manifest,
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
            fhir, manifest = self._copy_delivery(root / "delivery")
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
                    output_root=output,
                    secret=self.secret,
                )
            quarantine = next((output / "quarantine").iterdir())
            report = json.loads(
                (quarantine / "contract_report.json").read_text(encoding="utf-8")
            )
            issues = json.loads(
                (quarantine / "validation_issues.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(issues[0]["code"], "CONTRACT_BREAKING_DRIFT")
            self.assertEqual(issues[0]["record_id"], "GenomicManifest")

    def test_checksum_mismatch_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copied_fhir, manifest = self._copy_delivery(root / "delivery")
            rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
            rows[0]["expected_sha256"] = "0" * 64
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

            output = root / "output"
            with self.assertRaisesRegex(ValueError, "quarantined"):
                run_pipeline(
                    fhir_path=copied_fhir,
                    genomic_manifest_path=manifest,
                    output_root=output,
                    secret=self.secret,
                )
            issue_files = list((output / "quarantine").glob("*/validation_issues.json"))
            self.assertEqual(len(issue_files), 1)
            issues = json.loads(issue_files[0].read_text(encoding="utf-8"))
            self.assertEqual(issues[0]["code"], "GENOMIC_CHECKSUM_MISMATCH")

    def test_operations_summary_combines_success_and_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            run_pipeline(
                fhir_path=self.fhir,
                genomic_manifest_path=self.manifest,
                output_root=output,
                secret=self.secret,
            )

            copied_fhir, manifest = self._copy_delivery(root / "invalid-delivery")
            rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
            rows[0]["expected_sha256"] = "0" * 64
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                run_pipeline(
                    fhir_path=copied_fhir,
                    genomic_manifest_path=manifest,
                    output_root=output,
                    secret=self.secret,
                )

            summary = build_operations_summary(output)
            dashboard = render_operations_html(summary)
            self.assertEqual(summary["successful_count"], 1)
            self.assertEqual(summary["quarantined_count"], 1)
            self.assertEqual(summary["status"], "ATTENTION")
            self.assertIn("QUARANTINED_DELIVERIES_PRESENT", json.dumps(summary))
            self.assertIn("Clinical–Genomic Pipeline Operations", dashboard)


if __name__ == "__main__":
    unittest.main()
