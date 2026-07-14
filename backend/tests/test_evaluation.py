from __future__ import annotations

from pathlib import Path

from app.evaluation import run_benchmark


def test_synthetic_benchmark_matches_manifest() -> None:
    root = Path(__file__).resolve().parents[2]
    result = run_benchmark(root / "benchmark" / "manifest.json", root / "samples")
    assert result["total_cases"] == 9
    assert result["exact_decision_accuracy"] == 1.0
    assert result["unsafe_triage_recall"] == 1.0
    assert result["automation_rate"] == 0.667
