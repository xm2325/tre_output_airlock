from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.rules.base import FileContext
from app.services.checker import OutputChecker


def run_benchmark(manifest_path: Path, samples_dir: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checker = OutputChecker()
    cases: list[dict[str, Any]] = []
    exact = 0
    unsafe = 0
    unsafe_triaged = 0
    automated = 0
    for item in manifest["cases"]:
        path = samples_dir / item["file"]
        result = checker.check(
            FileContext(
                path=path,
                filename=path.name,
                content_type="application/octet-stream",
                size_bytes=path.stat().st_size,
            )
        )
        match = result.decision == item["expected_decision"]
        exact += int(match)
        is_unsafe = bool(item["unsafe"])
        unsafe += int(is_unsafe)
        unsafe_triaged += int(is_unsafe and result.decision in {"REVIEW", "BLOCK"})
        automated += int(result.decision in {"ALLOW", "BLOCK"})
        cases.append(
            {
                "file": item["file"],
                "expected": item["expected_decision"],
                "actual": result.decision,
                "unsafe": is_unsafe,
                "match": match,
                "finding_codes": [finding.code for finding in result.findings],
            }
        )
    total = len(cases)
    return {
        "benchmark_version": manifest["benchmark_version"],
        "total_cases": total,
        "exact_decision_accuracy": round(exact / total, 3) if total else 0.0,
        "unsafe_triage_recall": round(unsafe_triaged / unsafe, 3) if unsafe else 0.0,
        "automation_rate": round(automated / total, 3) if total else 0.0,
        "cases": cases,
        "limitations": (
            "Synthetic cases validate code paths only; they do not estimate performance "
            "on real research outputs."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("../benchmark/manifest.json"))
    parser.add_argument("--samples", type=Path, default=Path("../samples"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-all-expected", action="store_true")
    args = parser.parse_args()
    result = run_benchmark(args.manifest, args.samples)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if args.require_all_expected and (
        result["exact_decision_accuracy"] != 1.0
        or result["unsafe_triage_recall"] != 1.0
    ):
        raise SystemExit("Synthetic benchmark did not meet required regression expectations.")


if __name__ == "__main__":
    main()
