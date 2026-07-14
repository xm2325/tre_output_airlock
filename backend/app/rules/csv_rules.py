from __future__ import annotations

import csv
from collections import Counter

from app.rules.base import FileContext, FindingResult
from app.rules.common import (
    DIRECT_IDENTIFIER_HEADERS,
    FREE_TEXT_HEADERS,
    SENSITIVE_HEADER_FRAGMENTS,
    normalise_header,
    scan_text,
)

MAX_ROWS_TO_SCAN = 10_000
SMALL_CELL_THRESHOLD = 5
FORMULA_PREFIXES = ("=", "+", "-", "@")


class CsvDisclosureRule:
    def evaluate(self, context: FileContext) -> list[FindingResult]:
        if context.path.suffix.lower() != ".csv":
            return []

        findings: list[FindingResult] = []
        try:
            with context.path.open(
                "r", encoding="utf-8-sig", errors="replace", newline=""
            ) as handle:
                reader = csv.DictReader(handle)
                raw_headers = reader.fieldnames or []
                headers = [normalise_header(header) for header in raw_headers]

                direct = sorted(set(headers) & DIRECT_IDENTIFIER_HEADERS)
                if direct:
                    findings.append(
                        FindingResult(
                            code="DIRECT_IDENTIFIER_COLUMN",
                            severity="CRITICAL",
                            message="A column name indicates participant-level identifying data.",
                            evidence=f"columns={','.join(direct)}",
                        )
                    )

                suspicious = sorted(
                    header
                    for header in headers
                    if any(fragment in header for fragment in SENSITIVE_HEADER_FRAGMENTS)
                    and header not in DIRECT_IDENTIFIER_HEADERS
                )
                if suspicious:
                    findings.append(
                        FindingResult(
                            code="SENSITIVE_COLUMN_NAME",
                            severity="HIGH",
                            message="One or more column names may represent sensitive data.",
                            evidence=f"columns={','.join(suspicious[:10])}",
                        )
                    )

                free_text = sorted(set(headers) & FREE_TEXT_HEADERS)
                if free_text:
                    findings.append(
                        FindingResult(
                            code="FREE_TEXT_COLUMN",
                            severity="MEDIUM",
                            message="Free-text columns require human confirmation before release.",
                            evidence=f"columns={','.join(free_text[:10])}; values_not_logged=true",
                        )
                    )

                rows: list[dict[str, str]] = []
                truncated = False
                for index, row in enumerate(reader):
                    if index >= MAX_ROWS_TO_SCAN:
                        truncated = True
                        break
                    rows.append({normalise_header(key): value or "" for key, value in row.items()})

            if truncated:
                findings.append(
                    FindingResult(
                        code="PARTIAL_SCAN",
                        severity="MEDIUM",
                        message="The CSV exceeded the row scan limit and requires manual review.",
                        evidence=f"rows_scanned={MAX_ROWS_TO_SCAN}; more_rows_present=true",
                    )
                )

            findings.extend(self._small_cell_findings(rows, headers))
            findings.extend(self._uniqueness_findings(rows, headers))
            findings.extend(self._formula_findings(rows))
            sample_text = "\n".join(" ".join(row.values()) for row in rows[:500])
            findings.extend(scan_text(sample_text, "csv_sample"))
        except (OSError, csv.Error) as exc:
            findings.append(
                FindingResult(
                    code="CSV_PARSE_ERROR",
                    severity="HIGH",
                    message="The CSV could not be parsed reliably and requires manual review.",
                    evidence=f"error_type={type(exc).__name__}",
                )
            )

        return findings

    @staticmethod
    def _small_cell_findings(rows: list[dict[str, str]], headers: list[str]) -> list[FindingResult]:
        findings: list[FindingResult] = []
        for header in headers:
            is_count_column = (
                header in {"n", "count", "frequency", "number"}
                or header.endswith(("_n", "_count", "_frequency", "_number"))
                or header.startswith(("count_", "frequency_", "number_"))
            )
            if not is_count_column:
                continue
            small_values = 0
            numeric_values = 0
            for row in rows:
                value = row.get(header, "").strip()
                try:
                    number = float(value)
                except ValueError:
                    continue
                numeric_values += 1
                if 0 < number < SMALL_CELL_THRESHOLD:
                    small_values += 1
            if small_values:
                findings.append(
                    FindingResult(
                        code="SMALL_CELL",
                        severity="HIGH",
                        message="Small aggregate cells may increase disclosure risk.",
                        evidence=(
                            f"column={header}; small_cells={small_values}; "
                            f"numeric_cells_scanned={numeric_values}; "
                            f"threshold={SMALL_CELL_THRESHOLD}"
                        ),
                    )
                )
        return findings

    @staticmethod
    def _uniqueness_findings(rows: list[dict[str, str]], headers: list[str]) -> list[FindingResult]:
        if len(rows) < 20:
            return []
        findings: list[FindingResult] = []
        for header in headers:
            values = [row.get(header, "").strip() for row in rows]
            non_empty = [value for value in values if value]
            if len(non_empty) < 20:
                continue
            counts = Counter(non_empty)
            unique_ratio = sum(count == 1 for count in counts.values()) / len(non_empty)
            if unique_ratio >= 0.95:
                findings.append(
                    FindingResult(
                        code="HIGH_UNIQUENESS_COLUMN",
                        severity="MEDIUM",
                        message=(
                            "A highly unique column may encode row-level rather than "
                            "aggregate data."
                        ),
                        evidence=(
                            f"column={header}; unique_ratio={unique_ratio:.3f}; "
                            f"non_empty_values={len(non_empty)}"
                        ),
                    )
                )
        return findings

    @staticmethod
    def _formula_findings(rows: list[dict[str, str]]) -> list[FindingResult]:
        formula_cells = 0
        affected_columns: set[str] = set()
        for row in rows:
            for header, value in row.items():
                stripped = value.lstrip()
                if stripped.startswith(FORMULA_PREFIXES):
                    formula_cells += 1
                    affected_columns.add(header)
        if not formula_cells:
            return []
        return [
            FindingResult(
                code="SPREADSHEET_FORMULA",
                severity="HIGH",
                message="Spreadsheet formula content may execute when the CSV is opened.",
                evidence=(
                    f"formula_cells={formula_cells}; "
                    f"columns={','.join(sorted(affected_columns)[:10])}; values_redacted=true"
                ),
            )
        ]
