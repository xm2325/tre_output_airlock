from __future__ import annotations

import re
from pathlib import Path

from app.rules.base import FileContext, FindingResult

ALLOWED_EXTENSIONS = {".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg"}

DIRECT_IDENTIFIER_HEADERS = {
    "participant_id",
    "patient_id",
    "subject_id",
    "record_id",
    "nhs_number",
    "email",
    "email_address",
    "phone",
    "phone_number",
    "full_name",
    "first_name",
    "last_name",
    "address",
    "postcode",
    "date_of_birth",
    "dob",
    "eid",
}
SENSITIVE_HEADER_FRAGMENTS = {
    "participant",
    "patient",
    "subject",
    "nhs",
    "email",
    "phone",
    "address",
    "postcode",
    "birth",
}
FREE_TEXT_HEADERS = {
    "note",
    "notes",
    "comment",
    "comments",
    "free_text",
    "description",
    "clinical_text",
}

TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "EMAIL_ADDRESS",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "Email-address-like value detected.",
    ),
    (
        "UK_PHONE_NUMBER",
        re.compile(r"(?<!\d)(?:\+44\s?\d{4}|0\d{4})\s?\d{3}\s?\d{3}(?!\d)"),
        "UK-phone-number-like value detected.",
    ),
    (
        "NHS_NUMBER_LIKE",
        re.compile(r"(?<!\d)\d{3}\s?\d{3}\s?\d{4}(?!\d)"),
        "Ten-digit identifier resembling an NHS number detected.",
    ),
    (
        "UK_POSTCODE_LIKE",
        re.compile(r"\b(?:GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b", re.IGNORECASE),
        "UK-postcode-like value detected.",
    ),
    (
        "DATE_OF_BIRTH_LIKE",
        re.compile(
            (
                r"\b(?:dob|date[ _-]?of[ _-]?birth)\s*[:=]\s*"
                r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
            ),
            re.IGNORECASE,
        ),
        "Labelled date-of-birth-like value detected.",
    ),
)


def normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def scan_text(text: str, source: str) -> list[FindingResult]:
    findings: list[FindingResult] = []
    for code, pattern, message in TEXT_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            findings.append(
                FindingResult(
                    code=code,
                    severity="CRITICAL",
                    message=message,
                    evidence=(
                        f"source={source}; matches={len(matches)}; matched_values_redacted=true"
                    ),
                )
            )
    return findings


class FileTypeRule:
    def evaluate(self, context: FileContext) -> list[FindingResult]:
        extension = Path(context.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            return [
                FindingResult(
                    code="UNSUPPORTED_FILE_TYPE",
                    severity="CRITICAL",
                    message="The file type is not permitted by this demonstration policy.",
                    evidence=f"extension={extension or '<none>'}",
                )
            ]
        return []


class FileSignatureRule:
    _SIGNATURES: dict[str, tuple[bytes, ...]] = {
        ".pdf": (b"%PDF-",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
    }

    def evaluate(self, context: FileContext) -> list[FindingResult]:
        extension = context.path.suffix.lower()
        try:
            prefix = context.path.read_bytes()[:16]
        except OSError as exc:
            return [
                FindingResult(
                    code="CONTENT_SIGNATURE_MISMATCH",
                    severity="CRITICAL",
                    message="The file bytes could not be inspected safely.",
                    evidence=f"error_type={type(exc).__name__}",
                )
            ]
        if extension in {".csv", ".txt"} and b"\x00" in prefix:
            return [
                FindingResult(
                    code="BINARY_TEXT_FILE",
                    severity="HIGH",
                    message="A text-based file contains unexpected binary null bytes.",
                    evidence="null_byte_in_prefix=true",
                )
            ]
        signatures = self._SIGNATURES.get(extension)
        if signatures and not any(prefix.startswith(signature) for signature in signatures):
            return [
                FindingResult(
                    code="CONTENT_SIGNATURE_MISMATCH",
                    severity="CRITICAL",
                    message="The file bytes do not match the filename extension.",
                    evidence=f"extension={extension}; signature_redacted=true",
                )
            ]
        return []
