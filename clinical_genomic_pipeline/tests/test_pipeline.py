from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from clinical_genomic_pipeline.fhir import transform_bundle, validate_bundle
from clinical_genomic_pipeline.hashing import pseudonymise
from clinical_genomic_pipeline.pipeline import run_pipeline


class ClinicalGenomicPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]
        self.fhir = self.root / "samples" / "fhir_bundle.json"
        self.manifest = self.root / "samples" / "genomic_manifest.csv"
        self.secret = "test-secret-at-least-16-characters"

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
            self.assertTrue((first.run_directory / "_SUCCESS").is_file())
            self.assertTrue((first.run_directory / "lineage.json").is_file())
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

            cohort_text = (first.run_directory / "gold" / "research_cohort.csv").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("patient-001", cohort_text)
            self.assertNotIn("specimen-001", cohort_text)
            self.assertNotIn("sample-001", cohort_text)

            second = run_pipeline(
                fhir_path=self.fhir,
                genomic_manifest_path=self.manifest,
                output_root=output,
                secret=self.secret,
            )
            self.assertTrue(second.reused_existing_run)
            self.assertEqual(first.run_id, second.run_id)

    def test_checksum_mismatch_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            delivery = Path(temporary) / "delivery"
            delivery.mkdir()
            copied_fhir = delivery / "fhir_bundle.json"
            copied_fhir.write_text(self.fhir.read_text(encoding="utf-8"), encoding="utf-8")
            genomics = delivery / "genomics"
            genomics.mkdir()
            vcf = genomics / "sample_001.vcf"
            vcf.write_text(
                (self.root / "samples" / "genomics" / "sample_001.vcf").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            manifest = delivery / "genomic_manifest.csv"
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "sample_id",
                        "patient_reference",
                        "specimen_reference",
                        "vcf_path",
                        "expected_sha256",
                        "assembly",
                    ]
                )
                writer.writerow(
                    [
                        "sample-001",
                        "patient-001",
                        "specimen-001",
                        "genomics/sample_001.vcf",
                        "0" * 64,
                        "GRCh38",
                    ]
                )

            output = Path(temporary) / "output"
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


if __name__ == "__main__":
    unittest.main()
