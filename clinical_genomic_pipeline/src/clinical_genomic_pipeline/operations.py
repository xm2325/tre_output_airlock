"""Operational summary and dependency-free HTML evidence for pipeline runs."""

from __future__ import annotations

import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _successful_runs(output_root: Path) -> list[dict[str, Any]]:
    runs_root = output_root / "runs"
    if not runs_root.is_dir():
        return []
    output: list[dict[str, Any]] = []
    directories = sorted(path for path in runs_root.iterdir() if path.is_dir())
    for directory in directories:
        if not (directory / "_SUCCESS").is_file():
            continue
        metrics = _read_json(directory / "metrics.json")
        contract = _read_json(directory / "contract_report.json")
        transfer = _read_json(directory / "transfer_report.json")
        quality = _read_json(directory / "data_quality_report.json")
        output.append(
            {
                "run_id": directory.name,
                "people_count": int(metrics.get("people_count", 0)),
                "sample_count": int(metrics.get("sample_count", 0)),
                "processing_time_ms": float(
                    metrics.get("processing_time_ms", 0.0)
                ),
                "warning_count": int(metrics.get("warning_count", 0)),
                "contract_status": str(contract.get("status", "UNKNOWN")),
                "contract_warning_count": int(
                    contract.get("warning_count", 0)
                ),
                "schema_fingerprint": str(
                    contract.get("schema_fingerprint", "")
                ),
                "transfer_status": str(transfer.get("status", "UNKNOWN")),
                "transfer_tool": str(transfer.get("tool", "UNKNOWN")),
                "transfer_retry_count": int(transfer.get("retry_count", 0)),
                "data_quality_status": str(
                    quality.get("status", "UNKNOWN")
                ),
                "terminology_mapping_coverage": float(
                    metrics.get("terminology_mapping_coverage", 0.0)
                ),
            }
        )
    return output


def _quarantined_runs(output_root: Path) -> list[dict[str, Any]]:
    quarantine_root = output_root / "quarantine"
    if not quarantine_root.is_dir():
        return []
    output: list[dict[str, Any]] = []
    directories = sorted(
        path for path in quarantine_root.iterdir() if path.is_dir()
    )
    for directory in directories:
        issue_path = directory / "validation_issues.json"
        issue_values = (
            json.loads(issue_path.read_text(encoding="utf-8"))
            if issue_path.is_file()
            else []
        )
        issues = issue_values if isinstance(issue_values, list) else []
        contract = _read_json(directory / "contract_report.json")
        transfer = _read_json(directory / "transfer_report.json")
        quality = _read_json(directory / "data_quality_report.json")
        output.append(
            {
                "run_id": directory.name,
                "issue_count": len(issues),
                "issue_codes": sorted(
                    {
                        str(issue.get("code", "UNKNOWN"))
                        for issue in issues
                        if isinstance(issue, dict)
                    }
                ),
                "contract_status": str(contract.get("status", "UNKNOWN")),
                "transfer_status": str(transfer.get("status", "UNKNOWN")),
                "data_quality_status": str(
                    quality.get("status", "UNKNOWN")
                ),
            }
        )
    return output


def build_operations_summary(
    output_root: Path,
    *,
    success_target: float = 0.95,
) -> dict[str, Any]:
    """Aggregate run, transfer, quality, quarantine and staging state."""
    if not 0 < success_target <= 1:
        raise ValueError("success_target must be in the interval (0, 1]")

    runs = _successful_runs(output_root)
    quarantines = _quarantined_runs(output_root)
    staging_root = output_root / ".staging"
    incomplete_count = (
        sum(path.is_dir() for path in staging_root.iterdir())
        if staging_root.is_dir()
        else 0
    )
    successful_count = len(runs)
    quarantined_count = len(quarantines)
    attempted_count = successful_count + quarantined_count
    success_rate = successful_count / attempted_count if attempted_count else 1.0
    warning_count = sum(int(run["warning_count"]) for run in runs)
    contract_warnings = sum(
        int(run["contract_warning_count"]) for run in runs
    )
    transfer_retries = sum(int(run["transfer_retry_count"]) for run in runs)
    quality_warnings = sum(
        run["data_quality_status"] == "WARN" for run in runs
    )
    total_samples = sum(int(run["sample_count"]) for run in runs)

    alerts: list[dict[str, str]] = []
    if success_rate < success_target:
        alerts.append(
            {
                "code": "SUCCESS_RATE_BELOW_TARGET",
                "severity": "ERROR",
                "message": (
                    f"Observed success rate {success_rate:.3f} is below target "
                    f"{success_target:.3f}."
                ),
            }
        )
    alert_specs = (
        (
            quarantined_count,
            "QUARANTINED_DELIVERIES_PRESENT",
            f"{quarantined_count} delivery or deliveries require investigation.",
        ),
        (
            contract_warnings,
            "CONTRACT_WARNINGS_PRESENT",
            f"{contract_warnings} additive schema change or changes were observed.",
        ),
        (
            quality_warnings,
            "DATA_QUALITY_WARNINGS_PRESENT",
            f"{quality_warnings} run or runs require terminology review.",
        ),
        (
            transfer_retries,
            "TRANSFER_RETRIES_PRESENT",
            f"{transfer_retries} transfer retry or retries were recorded.",
        ),
        (
            incomplete_count,
            "INCOMPLETE_STAGING_PRESENT",
            f"{incomplete_count} incomplete staging directory or directories remain.",
        ),
    )
    for count, code, message in alert_specs:
        if count:
            severity = "ERROR" if code == "INCOMPLETE_STAGING_PRESENT" else "WARNING"
            alerts.append({"code": code, "severity": severity, "message": message})

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "HEALTHY" if not alerts else "ATTENTION",
        "success_target": success_target,
        "successful_count": successful_count,
        "quarantined_count": quarantined_count,
        "attempted_count": attempted_count,
        "success_rate": round(success_rate, 6),
        "warning_count": warning_count,
        "contract_warning_count": contract_warnings,
        "data_quality_warning_count": quality_warnings,
        "transfer_retry_count": transfer_retries,
        "incomplete_staging_count": incomplete_count,
        "total_samples_published": total_samples,
        "alerts": alerts,
        "runs": runs,
        "quarantines": quarantines,
    }


def _run_rows(summary: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(run['run_id']))}</code></td>"
        f"<td>{int(run['sample_count'])}</td>"
        f"<td>{html.escape(str(run['transfer_tool']))}</td>"
        f"<td>{html.escape(str(run['contract_status']))}</td>"
        f"<td>{html.escape(str(run['data_quality_status']))}</td>"
        f"<td>{float(run['terminology_mapping_coverage']):.1%}</td>"
        f"<td>{float(run['processing_time_ms']):.3f}</td>"
        "</tr>"
        for run in summary.get("runs", [])
    )
    return rows or '<tr><td colspan="7">No successful runs recorded.</td></tr>'


def _quarantine_rows(summary: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(item['run_id']))}</code></td>"
        f"<td>{int(item['issue_count'])}</td>"
        f"<td>{html.escape(', '.join(map(str, item['issue_codes'])))}</td>"
        f"<td>{html.escape(str(item['transfer_status']))}</td>"
        "</tr>"
        for item in summary.get("quarantines", [])
    )
    return rows or '<tr><td colspan="4">No quarantined deliveries recorded.</td></tr>'


def render_operations_html(summary: dict[str, Any]) -> str:
    """Render a portable operations dashboard with no remote assets."""
    alert_items = "".join(
        "<li>"
        f"<strong>{html.escape(str(alert['severity']))}: "
        f"{html.escape(str(alert['code']))}</strong> — "
        f"{html.escape(str(alert['message']))}"
        "</li>"
        for alert in summary.get("alerts", [])
    ) or "<li>No active operational alerts.</li>"
    generated_at = html.escape(str(summary["generated_at"]))
    status = html.escape(str(summary["status"]))
    success_rate = f"{float(summary['success_rate']):.1%}"
    cards = (
        ("Status", status),
        ("Success rate", success_rate),
        ("Successful runs", str(int(summary["successful_count"]))),
        ("Quarantined", str(int(summary["quarantined_count"]))),
        ("Warnings", str(int(summary["warning_count"]))),
        ("Samples published", str(int(summary["total_samples_published"]))),
    )
    card_html = "".join(
        f'<div class="card"><div>{label}</div><div class="value">{value}</div></div>'
        for label, value in cards
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clinical–Genomic Pipeline Operations</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #f4f6f8; }}
    main {{ max-width: 1180px; margin: auto; padding: 32px 20px 56px; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
    .card, section {{ background: white; border: 1px solid #d8dee5; padding: 18px; }}
    .value {{ font-size: 1.8rem; font-weight: 700; margin-top: 6px; }}
    section {{ margin-top: 18px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e7ebef; padding: 10px 8px; }}
  </style>
</head>
<body>
<main>
  <h1>Clinical–Genomic Pipeline Operations</h1>
  <p>Generated {generated_at}. Synthetic demonstration data only.</p>
  <div class="cards">{card_html}</div>
  <section><h2>Alerts</h2><ul>{alert_items}</ul></section>
  <section>
    <h2>Successful runs</h2>
    <table>
      <thead><tr><th>Run</th><th>Samples</th><th>Transfer</th>
      <th>Contract</th><th>Quality</th><th>Mapped</th><th>Time</th></tr></thead>
      <tbody>{_run_rows(summary)}</tbody>
    </table>
  </section>
  <section>
    <h2>Quarantine</h2>
    <table><thead><tr><th>Run</th><th>Issues</th><th>Codes</th>
    <th>Transfer</th></tr></thead><tbody>{_quarantine_rows(summary)}</tbody></table>
  </section>
</main>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build clinical-genomic operations evidence"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--success-target", type=float, default=0.95)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = build_operations_summary(
        args.output,
        success_target=args.success_target,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.html.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    args.json.write_text(json_text, encoding="utf-8")
    args.html.write_text(render_operations_html(summary), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
