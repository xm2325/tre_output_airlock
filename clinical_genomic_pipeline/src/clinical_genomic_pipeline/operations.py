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


def build_operations_summary(
    output_root: Path,
    *,
    success_target: float = 0.95,
) -> dict[str, Any]:
    """Aggregate successful runs, quarantines, contract warnings and alerts."""
    if not 0 < success_target <= 1:
        raise ValueError("success_target must be in the interval (0, 1]")

    runs: list[dict[str, Any]] = []
    runs_root = output_root / "runs"
    if runs_root.is_dir():
        for run_directory in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            if not (run_directory / "_SUCCESS").is_file():
                continue
            metrics = _read_json(run_directory / "metrics.json")
            contract = _read_json(run_directory / "contract_report.json")
            runs.append(
                {
                    "run_id": run_directory.name,
                    "people_count": int(metrics.get("people_count", 0)),
                    "sample_count": int(metrics.get("sample_count", 0)),
                    "processing_time_ms": float(metrics.get("processing_time_ms", 0.0)),
                    "contract_status": str(contract.get("status", "UNKNOWN")),
                    "contract_warning_count": int(contract.get("warning_count", 0)),
                    "schema_fingerprint": str(contract.get("schema_fingerprint", "")),
                }
            )

    quarantines: list[dict[str, Any]] = []
    quarantine_root = output_root / "quarantine"
    if quarantine_root.is_dir():
        for quarantine_directory in sorted(
            path for path in quarantine_root.iterdir() if path.is_dir()
        ):
            issue_path = quarantine_directory / "validation_issues.json"
            issue_values = json.loads(issue_path.read_text(encoding="utf-8")) if issue_path.is_file() else []
            issues = issue_values if isinstance(issue_values, list) else []
            quarantines.append(
                {
                    "run_id": quarantine_directory.name,
                    "issue_count": len(issues),
                    "issue_codes": sorted(
                        {
                            str(issue.get("code", "UNKNOWN"))
                            for issue in issues
                            if isinstance(issue, dict)
                        }
                    ),
                    "contract_status": str(
                        _read_json(quarantine_directory / "contract_report.json").get(
                            "status", "UNKNOWN"
                        )
                    ),
                }
            )

    incomplete_staging_count = 0
    staging_root = output_root / ".staging"
    if staging_root.is_dir():
        incomplete_staging_count = sum(path.is_dir() for path in staging_root.iterdir())

    successful_count = len(runs)
    quarantined_count = len(quarantines)
    attempted_count = successful_count + quarantined_count
    success_rate = successful_count / attempted_count if attempted_count else 1.0
    warning_count = sum(int(run["contract_warning_count"]) for run in runs)
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
    if quarantined_count:
        alerts.append(
            {
                "code": "QUARANTINED_DELIVERIES_PRESENT",
                "severity": "WARNING",
                "message": f"{quarantined_count} delivery or deliveries require investigation.",
            }
        )
    if warning_count:
        alerts.append(
            {
                "code": "CONTRACT_WARNINGS_PRESENT",
                "severity": "WARNING",
                "message": f"{warning_count} additive schema change or changes were observed.",
            }
        )
    if incomplete_staging_count:
        alerts.append(
            {
                "code": "INCOMPLETE_STAGING_PRESENT",
                "severity": "ERROR",
                "message": f"{incomplete_staging_count} incomplete staging directory or directories remain.",
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "HEALTHY" if not alerts else "ATTENTION",
        "success_target": success_target,
        "successful_count": successful_count,
        "quarantined_count": quarantined_count,
        "attempted_count": attempted_count,
        "success_rate": round(success_rate, 6),
        "contract_warning_count": warning_count,
        "incomplete_staging_count": incomplete_staging_count,
        "total_samples_published": total_samples,
        "alerts": alerts,
        "runs": runs,
        "quarantines": quarantines,
    }


def render_operations_html(summary: dict[str, Any]) -> str:
    """Render a portable operations dashboard with no remote assets."""
    run_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(run['run_id']))}</code></td>"
        f"<td>{int(run['sample_count'])}</td>"
        f"<td>{html.escape(str(run['contract_status']))}</td>"
        f"<td>{int(run['contract_warning_count'])}</td>"
        f"<td>{float(run['processing_time_ms']):.3f}</td>"
        "</tr>"
        for run in summary.get("runs", [])
    ) or '<tr><td colspan="5">No successful runs recorded.</td></tr>'

    quarantine_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(item['run_id']))}</code></td>"
        f"<td>{int(item['issue_count'])}</td>"
        f"<td>{html.escape(', '.join(str(code) for code in item['issue_codes']))}</td>"
        f"<td>{html.escape(str(item['contract_status']))}</td>"
        "</tr>"
        for item in summary.get("quarantines", [])
    ) or '<tr><td colspan="4">No quarantined deliveries recorded.</td></tr>'

    alert_items = "".join(
        "<li>"
        f"<strong>{html.escape(str(alert['severity']))}: "
        f"{html.escape(str(alert['code']))}</strong> — "
        f"{html.escape(str(alert['message']))}"
        "</li>"
        for alert in summary.get("alerts", [])
    ) or "<li>No active operational alerts.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clinical–Genomic Pipeline Operations</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #f4f6f8; color: #18212b; }}
    main {{ max-width: 1120px; margin: auto; padding: 32px 20px 56px; }}
    h1, h2 {{ margin-bottom: 0.4rem; }}
    .muted {{ color: #52606d; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 24px 0; }}
    .card, section {{ background: white; border: 1px solid #d8dee5; border-radius: 10px; padding: 18px; }}
    .value {{ font-size: 1.8rem; font-weight: 700; margin-top: 6px; }}
    section {{ margin-top: 18px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e7ebef; padding: 10px 8px; }}
    th {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    code {{ font-size: 0.9em; }}
  </style>
</head>
<body>
<main>
  <h1>Clinical–Genomic Pipeline Operations</h1>
  <p class="muted">Generated {html.escape(str(summary['generated_at']))}. Synthetic demonstration data only.</p>
  <div class="cards">
    <div class="card"><div>Status</div><div class="value">{html.escape(str(summary['status']))}</div></div>
    <div class="card"><div>Success rate</div><div class="value">{float(summary['success_rate']):.1%}</div></div>
    <div class="card"><div>Successful runs</div><div class="value">{int(summary['successful_count'])}</div></div>
    <div class="card"><div>Quarantined</div><div class="value">{int(summary['quarantined_count'])}</div></div>
    <div class="card"><div>Contract warnings</div><div class="value">{int(summary['contract_warning_count'])}</div></div>
    <div class="card"><div>Samples published</div><div class="value">{int(summary['total_samples_published'])}</div></div>
  </div>
  <section><h2>Alerts</h2><ul>{alert_items}</ul></section>
  <section>
    <h2>Successful runs</h2>
    <table><thead><tr><th>Run</th><th>Samples</th><th>Contract</th><th>Warnings</th><th>Time (ms)</th></tr></thead>
    <tbody>{run_rows}</tbody></table>
  </section>
  <section>
    <h2>Quarantine</h2>
    <table><thead><tr><th>Run</th><th>Issues</th><th>Codes</th><th>Contract</th></tr></thead>
    <tbody>{quarantine_rows}</tbody></table>
  </section>
</main>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build clinical-genomic operations evidence")
    parser.add_argument("--output", type=Path, required=True, help="Pipeline output root")
    parser.add_argument("--json", type=Path, required=True, help="Summary JSON destination")
    parser.add_argument("--html", type=Path, required=True, help="Dashboard HTML destination")
    parser.add_argument("--success-target", type=float, default=0.95)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = build_operations_summary(args.output, success_target=args.success_target)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.html.write_text(render_operations_html(summary), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
