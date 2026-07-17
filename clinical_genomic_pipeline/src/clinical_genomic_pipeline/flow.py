"""Prefect orchestration with explicit preflight, processing and evidence tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

try:
    from prefect import flow, task
except ImportError as exc:  # pragma: no cover - optional dependency boundary
    raise RuntimeError(
        "Install the orchestration extra: pip install -e '.[orchestration]'"
    ) from exc

from .contracts import evaluate_contract
from .genomics import load_manifest
from .models import PipelineResult
from .pipeline import run_pipeline
from .transfer import validate_transfer_receipt


@task(retries=3, retry_delay_seconds=5, task_run_name="delivery-preflight")
def preflight_delivery(
    fhir_path: str,
    genomic_manifest_path: str,
    transfer_receipt_path: str,
) -> dict[str, Any]:
    """Check contract and transfer evidence before a processing worker starts."""
    fhir = Path(fhir_path).resolve()
    manifest = Path(genomic_manifest_path).resolve()
    receipt = Path(transfer_receipt_path).resolve()
    bundle_value: Any = json.loads(fhir.read_text(encoding="utf-8"))
    if not isinstance(bundle_value, dict):
        raise ValueError("FHIR input must be a JSON object")
    contract = evaluate_contract(bundle_value, manifest)
    if contract["status"] == "FAIL":
        raise ValueError("Preflight failed: breaking data-contract drift")

    rows = load_manifest(manifest)
    genomic_files = [(manifest.parent / row.vcf_path).resolve() for row in rows]
    transfer, issues = validate_transfer_receipt(
        receipt_path=receipt,
        delivery_root=manifest.parent,
        expected_files=[fhir, manifest, *genomic_files],
    )
    if issues:
        raise ValueError(f"Preflight failed with {len(issues)} transfer issue(s)")
    return {
        "contract_status": contract["status"],
        "schema_fingerprint": contract["schema_fingerprint"],
        "transfer_id": transfer["transfer_id"],
        "transfer_tool": transfer["tool"],
        "transfer_bytes": transfer["total_bytes"],
    }


@task(retries=2, retry_delay_seconds=10, task_run_name="clinical-genomic-processing")
def process_delivery(
    fhir_path: str,
    genomic_manifest_path: str,
    transfer_receipt_path: str,
    terminology_map_path: str,
    output_root: str,
    secret: str,
) -> PipelineResult:
    """Run one repeatable clinical-genomic transformation and publication."""
    return run_pipeline(
        fhir_path=Path(fhir_path),
        genomic_manifest_path=Path(genomic_manifest_path),
        transfer_receipt_path=Path(transfer_receipt_path),
        terminology_map_path=Path(terminology_map_path),
        output_root=Path(output_root),
        secret=secret,
    )


@task(task_run_name="run-evidence-summary")
def summarise_run(result: PipelineResult) -> dict[str, Any]:
    """Read the committed evidence used by product, QA and operations teams."""
    metrics = json.loads((result.run_directory / "metrics.json").read_text(encoding="utf-8"))
    quality = json.loads(
        (result.run_directory / "data_quality_report.json").read_text(encoding="utf-8")
    )
    return {
        "run_id": result.run_id,
        "reused": result.reused_existing_run,
        "sample_count": result.sample_count,
        "warning_count": result.warning_count,
        "data_quality_status": quality["status"],
        "terminology_mapping_coverage": metrics["terminology_mapping_coverage"],
    }


@flow(name="clinical-genomic-ingestion", log_prints=True)
def clinical_genomic_flow(
    fhir_path: str,
    genomic_manifest_path: str,
    transfer_receipt_path: str,
    terminology_map_path: str,
    output_root: str,
    secret: str,
) -> PipelineResult:
    """Orchestrate preflight, processing and operational evidence."""
    preflight = cast(
        dict[str, Any],
        preflight_delivery(fhir_path, genomic_manifest_path, transfer_receipt_path),
    )
    result = cast(
        PipelineResult,
        process_delivery(
            fhir_path,
            genomic_manifest_path,
            transfer_receipt_path,
            terminology_map_path,
            output_root,
            secret,
        ),
    )
    summary = cast(dict[str, Any], summarise_run(result))
    print(
        f"transfer={preflight['transfer_tool']}:{preflight['transfer_id']} "
        f"run_id={summary['run_id']} samples={summary['sample_count']} "
        f"quality={summary['data_quality_status']} reused={summary['reused']}"
    )
    return result
