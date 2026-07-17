"""Prefect orchestration wrapper with retry and observable task boundaries."""

from __future__ import annotations

from pathlib import Path

try:
    from prefect import flow, task
except ImportError as exc:  # pragma: no cover - optional dependency boundary
    raise RuntimeError(
        "Install the orchestration extra: pip install -e '.[orchestration]'"
    ) from exc

from .pipeline import PipelineResult, run_pipeline


@task(retries=2, retry_delay_seconds=5, task_run_name="clinical-genomic-delivery")
def process_delivery(
    fhir_path: str,
    genomic_manifest_path: str,
    output_root: str,
    secret: str,
) -> PipelineResult:
    """Run one repeatable delivery task."""
    return run_pipeline(
        fhir_path=Path(fhir_path),
        genomic_manifest_path=Path(genomic_manifest_path),
        output_root=Path(output_root),
        secret=secret,
    )


@flow(name="clinical-genomic-ingestion", log_prints=True)
def clinical_genomic_flow(
    fhir_path: str,
    genomic_manifest_path: str,
    output_root: str,
    secret: str,
) -> PipelineResult:
    """Orchestrate one clinical-genomic delivery."""
    result = process_delivery(fhir_path, genomic_manifest_path, output_root, secret)
    print(
        f"run_id={result.run_id} people={result.people_count} "
        f"samples={result.sample_count} reused={result.reused_existing_run}"
    )
    return result
