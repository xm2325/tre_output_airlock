from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

FIXTURE_PROJECT = "CURSOR-PLAN-CI"
CREATED_INDEX = "ix_submissions_created_id"
RISK_INDEX = "ix_submissions_risk_cursor"


def _collect_indexes(node: dict[str, Any]) -> set[str]:
    indexes: set[str] = set()
    index_name = node.get("Index Name")
    if isinstance(index_name, str):
        indexes.add(index_name)
    for child in node.get("Plans", []):
        if isinstance(child, dict):
            indexes.update(_collect_indexes(child))
    return indexes


def _plan(connection: Any, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    raw = connection.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"), params).scalar_one()
    decoded = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(decoded, list) or not decoded or not isinstance(decoded[0], dict):
        raise RuntimeError("PostgreSQL returned an unexpected EXPLAIN JSON shape.")
    plan = decoded[0]
    if not isinstance(plan.get("Plan"), dict):
        raise RuntimeError("PostgreSQL EXPLAIN JSON did not contain a plan tree.")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that PostgreSQL uses Airlock cursor indexes for deep keyset queries."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=20_000)
    args = parser.parse_args()
    if args.rows < 5_000:
        parser.error("--rows must be at least 5000 so the planner sees a non-trivial relation.")

    database_url = os.environ.get("AIRLOCK_DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        raise SystemExit("AIRLOCK_DATABASE_URL must target PostgreSQL for this contract.")

    engine = create_engine(database_url)
    anchor_row = args.rows // 2
    anchor_id = str(anchor_row).rjust(36, "0")

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM submissions WHERE project_code = :project"),
            {"project": FIXTURE_PROJECT},
        )
        connection.execute(
            text(
                """
                INSERT INTO submissions (
                    id, project_code, output_type, output_description, filename,
                    content_type, size_bytes, sha256, status, automated_decision,
                    risk_score, policy_version, submitted_by, row_version,
                    created_at, updated_at
                )
                SELECT
                    lpad(gs::text, 36, '0'),
                    :project,
                    'TABLE',
                    'Synthetic PostgreSQL query-plan fixture.',
                    'plan-' || gs::text || '.csv',
                    'text/csv',
                    100,
                    md5(gs::text) || md5(gs::text || '-cursor-plan'),
                    'COMPLETED',
                    'ALLOW',
                    gs::double precision / :rows,
                    'cursor-plan-ci',
                    'plan-fixture',
                    1,
                    TIMESTAMPTZ '2026-01-01 00:00:00+00' + gs * INTERVAL '1 second',
                    TIMESTAMPTZ '2026-01-01 00:00:00+00' + gs * INTERVAL '1 second'
                FROM generate_series(1, :rows) AS gs
                """
            ),
            {"project": FIXTURE_PROJECT, "rows": args.rows},
        )
        connection.execute(text("ANALYZE submissions"))

        anchor = connection.execute(
            text(
                """
                SELECT created_at, risk_score
                FROM submissions
                WHERE id = :anchor_id AND project_code = :project
                """
            ),
            {"anchor_id": anchor_id, "project": FIXTURE_PROJECT},
        ).one()

        newest_sql = """
            SELECT id
            FROM submissions
            WHERE project_code = :project
              AND (
                    created_at < :created_at
                    OR (created_at = :created_at AND id < :anchor_id)
              )
            ORDER BY created_at DESC, id DESC
            LIMIT 25
        """
        risk_sql = """
            SELECT id
            FROM submissions
            WHERE project_code = :project
              AND (
                    risk_score < :risk_score
                    OR (risk_score = :risk_score AND created_at > :created_at)
                    OR (
                        risk_score = :risk_score
                        AND created_at = :created_at
                        AND id > :anchor_id
                    )
              )
            ORDER BY risk_score DESC, created_at ASC, id ASC
            LIMIT 25
        """
        params = {
            "project": FIXTURE_PROJECT,
            "created_at": anchor.created_at,
            "risk_score": anchor.risk_score,
            "anchor_id": anchor_id,
        }
        newest = _plan(connection, newest_sql, params)
        risk = _plan(connection, risk_sql, params)

    newest_indexes = sorted(_collect_indexes(newest["Plan"]))
    risk_indexes = sorted(_collect_indexes(risk["Plan"]))
    evidence = {
        "contract": "postgresql-cursor-query-plan-v1",
        "fixture_rows": args.rows,
        "anchor_row": anchor_row,
        "queries": [
            {
                "name": "newest",
                "required_index": CREATED_INDEX,
                "indexes_used": newest_indexes,
                "explain": newest,
            },
            {
                "name": "risk_desc",
                "required_index": RISK_INDEX,
                "indexes_used": risk_indexes,
                "explain": risk,
            },
        ],
        "boundary": (
            "Synthetic PostgreSQL CI evidence for planner/index selection only; "
            "not a production latency or throughput benchmark."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + "\n")

    missing: list[str] = []
    if CREATED_INDEX not in newest_indexes:
        missing.append(f"newest did not use {CREATED_INDEX}: {newest_indexes}")
    if RISK_INDEX not in risk_indexes:
        missing.append(f"risk_desc did not use {RISK_INDEX}: {risk_indexes}")
    if missing:
        raise SystemExit("; ".join(missing))

    print(f"newest indexes: {', '.join(newest_indexes)}")
    print(f"risk_desc indexes: {', '.join(risk_indexes)}")
    print(f"wrote query-plan evidence to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
