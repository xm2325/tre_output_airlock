from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PolicyAction = Literal["ALLOW", "REVIEW", "BLOCK"]

API_VERSION = "0.3.1"
POLICY_VERSION = "demo-policy-2026.2"


@dataclass(frozen=True)
class RuleDefinition:
    code: str
    category: str
    severity: str
    title: str
    description: str
    default_action: PolicyAction


RULE_CATALOG: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        "UNSUPPORTED_FILE_TYPE",
        "file-integrity",
        "CRITICAL",
        "Unsupported file type",
        "The filename extension is outside the demonstration allow-list.",
        "BLOCK",
    ),
    RuleDefinition(
        "CONTENT_SIGNATURE_MISMATCH",
        "file-integrity",
        "CRITICAL",
        "File signature mismatch",
        "The file bytes do not match the declared filename extension.",
        "BLOCK",
    ),
    RuleDefinition(
        "BINARY_TEXT_FILE",
        "file-integrity",
        "HIGH",
        "Unexpected binary content",
        "A CSV or text file contains null bytes and cannot be treated as plain text safely.",
        "REVIEW",
    ),
    RuleDefinition(
        "DIRECT_IDENTIFIER_COLUMN",
        "direct-identifiers",
        "CRITICAL",
        "Direct identifier column",
        "A column name indicates participant-level identifying data.",
        "BLOCK",
    ),
    RuleDefinition(
        "SENSITIVE_COLUMN_NAME",
        "sensitive-fields",
        "HIGH",
        "Sensitive column name",
        "A column name may represent sensitive or participant-level data.",
        "REVIEW",
    ),
    RuleDefinition(
        "FREE_TEXT_COLUMN",
        "sensitive-fields",
        "MEDIUM",
        "Free-text column",
        "A free-text column can contain identifiers that are hard to validate automatically.",
        "REVIEW",
    ),
    RuleDefinition(
        "EMAIL_ADDRESS",
        "direct-identifiers",
        "CRITICAL",
        "Email-address-like value",
        "An email-address-like value was detected in scanned content.",
        "BLOCK",
    ),
    RuleDefinition(
        "UK_PHONE_NUMBER",
        "direct-identifiers",
        "CRITICAL",
        "UK-phone-number-like value",
        "A UK-phone-number-like value was detected in scanned content.",
        "BLOCK",
    ),
    RuleDefinition(
        "NHS_NUMBER_LIKE",
        "direct-identifiers",
        "CRITICAL",
        "NHS-number-like value",
        "A ten-digit identifier resembling an NHS number was detected.",
        "BLOCK",
    ),
    RuleDefinition(
        "UK_POSTCODE_LIKE",
        "quasi-identifiers",
        "CRITICAL",
        "UK-postcode-like value",
        "A UK-postcode-like value was detected in scanned content.",
        "BLOCK",
    ),
    RuleDefinition(
        "DATE_OF_BIRTH_LIKE",
        "quasi-identifiers",
        "CRITICAL",
        "Date-of-birth-like value",
        "A labelled date-of-birth-like value was detected in scanned content.",
        "BLOCK",
    ),
    RuleDefinition(
        "SMALL_CELL",
        "statistical-disclosure",
        "HIGH",
        "Small aggregate cell",
        "An aggregate count is below the demonstration threshold.",
        "REVIEW",
    ),
    RuleDefinition(
        "HIGH_UNIQUENESS_COLUMN",
        "statistical-disclosure",
        "MEDIUM",
        "Highly unique column",
        "A column contains a high proportion of unique values and may encode row-level data.",
        "REVIEW",
    ),
    RuleDefinition(
        "SPREADSHEET_FORMULA",
        "active-content",
        "HIGH",
        "Spreadsheet formula content",
        "A cell starts with a spreadsheet formula prefix and may execute when opened.",
        "REVIEW",
    ),
    RuleDefinition(
        "PARTIAL_SCAN",
        "coverage",
        "MEDIUM",
        "Partial content scan",
        "The file exceeded the row scan limit, so automated coverage is incomplete.",
        "REVIEW",
    ),
    RuleDefinition(
        "CSV_PARSE_ERROR",
        "file-integrity",
        "HIGH",
        "CSV parse failure",
        "The CSV could not be parsed reliably.",
        "REVIEW",
    ),
    RuleDefinition(
        "TEXT_READ_ERROR",
        "file-integrity",
        "HIGH",
        "Text read failure",
        "The text file could not be read reliably.",
        "REVIEW",
    ),
    RuleDefinition(
        "PDF_METADATA_PRESENT",
        "metadata",
        "LOW",
        "PDF metadata present",
        "PDF metadata exists and should be checked before release.",
        "ALLOW",
    ),
    RuleDefinition(
        "PDF_PARSE_ERROR",
        "file-integrity",
        "HIGH",
        "PDF parse failure",
        "The PDF could not be parsed reliably.",
        "REVIEW",
    ),
    RuleDefinition(
        "IMAGE_GPS_METADATA",
        "metadata",
        "CRITICAL",
        "Image GPS metadata",
        "Image metadata contains location information.",
        "BLOCK",
    ),
    RuleDefinition(
        "IMAGE_METADATA_PRESENT",
        "metadata",
        "LOW",
        "Image metadata present",
        "Image metadata exists and should be removed or checked.",
        "ALLOW",
    ),
    RuleDefinition(
        "IMAGE_PARSE_ERROR",
        "file-integrity",
        "HIGH",
        "Image parse failure",
        "The image could not be parsed reliably.",
        "REVIEW",
    ),
    RuleDefinition(
        "DUPLICATE_FILE_HASH",
        "workflow",
        "LOW",
        "Duplicate file fingerprint",
        "The same SHA-256 fingerprint has been submitted previously.",
        "ALLOW",
    ),
)

RULE_BY_CODE = {item.code: item for item in RULE_CATALOG}


def risk_band(score: float) -> str:
    if score >= 1.0:
        return "CRITICAL"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.25:
        return "MODERATE"
    return "LOW"
