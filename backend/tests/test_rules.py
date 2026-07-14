from __future__ import annotations

from pathlib import Path

from app.rules.base import FileContext
from app.services.checker import OutputChecker


def check_file(tmp_path: Path, name: str, content: bytes):
    path = tmp_path / name
    path.write_bytes(content)
    return OutputChecker().check(
        FileContext(
            path=path,
            filename=path.name,
            content_type="application/octet-stream",
            size_bytes=path.stat().st_size,
        )
    )


def check_csv(tmp_path: Path, content: str):
    return check_file(tmp_path, "sample.csv", content.encode("utf-8"))


def test_safe_aggregate_csv_is_allowed(tmp_path: Path) -> None:
    result = check_csv(tmp_path, "group,mean_age\nA,50.1\nB,52.4\n")
    assert result.decision == "ALLOW"
    assert result.risk_band == "LOW"


def test_participant_identifier_column_is_blocked(tmp_path: Path) -> None:
    result = check_csv(tmp_path, "participant_id,value\nP001,2.1\nP002,2.4\n")
    assert result.decision == "BLOCK"
    assert any(item.code == "DIRECT_IDENTIFIER_COLUMN" for item in result.findings)


def test_small_cells_require_review(tmp_path: Path) -> None:
    result = check_csv(tmp_path, "group,count\nA,2\nB,17\n")
    assert result.decision == "REVIEW"
    assert any(item.code == "SMALL_CELL" for item in result.findings)


def test_email_value_is_blocked_without_echoing_value(tmp_path: Path) -> None:
    result = check_csv(tmp_path, "group,note\nA,person@example.org\n")
    assert result.decision == "BLOCK"
    finding = next(item for item in result.findings if item.code == "EMAIL_ADDRESS")
    assert "person@example.org" not in (finding.evidence or "")


def test_postcode_and_dob_are_blocked_without_echoing_values(tmp_path: Path) -> None:
    postcode = check_file(tmp_path, "postcode.txt", b"Location: M13 9PL")
    assert postcode.decision == "BLOCK"
    assert any(item.code == "UK_POSTCODE_LIKE" for item in postcode.findings)
    assert "M13 9PL" not in " ".join(item.evidence or "" for item in postcode.findings)

    dob = check_file(tmp_path, "dob.txt", b"date of birth: 12/04/1975")
    assert dob.decision == "BLOCK"
    assert any(item.code == "DATE_OF_BIRTH_LIKE" for item in dob.findings)


def test_free_text_column_requires_review_even_without_identifier(tmp_path: Path) -> None:
    result = check_csv(tmp_path, "group,notes\nA,synthetic summary only\n")
    assert result.decision == "REVIEW"
    assert any(item.code == "FREE_TEXT_COLUMN" for item in result.findings)


def test_high_uniqueness_requires_review(tmp_path: Path) -> None:
    rows = "\n".join(f"G{i},{100 + i}" for i in range(20))
    result = check_csv(tmp_path, f"label,estimate\n{rows}\n")
    assert result.decision == "REVIEW"
    assert any(item.code == "HIGH_UNIQUESS_COLUMN" for item in result.findings) is False
    assert any(item.code == "HIGH_UNIQUENESS_COLUMN" for item in result.findings)


def test_spreadsheet_formula_requires_review_and_redacts_value(tmp_path: Path) -> None:
    result = check_csv(tmp_path, 'group,note\nA,=HYPERLINK("https://example.org")\n')
    assert result.decision == "REVIEW"
    finding = next(item for item in result.findings if item.code == "SPREADSHEET_FORMULA")
    assert "HYPERLINK" not in (finding.evidence or "")


def test_fake_png_is_blocked_by_signature_rule(tmp_path: Path) -> None:
    result = check_file(tmp_path, "fake.png", b"not-a-png")
    assert result.decision == "BLOCK"
    assert any(item.code == "CONTENT_SIGNATURE_MISMATCH" for item in result.findings)


def test_binary_text_file_requires_review(tmp_path: Path) -> None:
    result = check_file(tmp_path, "binary.txt", b"abc\x00def")
    assert result.decision == "REVIEW"
    assert any(item.code == "BINARY_TEXT_FILE" for item in result.findings)


def test_invalid_pdf_signature_does_not_add_parser_noise(tmp_path: Path) -> None:
    result = check_file(tmp_path, "fake.pdf", b"not-a-pdf")
    codes = [item.code for item in result.findings]
    assert codes == ["CONTENT_SIGNATURE_MISMATCH"]


def test_invalid_image_signature_does_not_add_parser_noise(tmp_path: Path) -> None:
    result = check_file(tmp_path, "fake.jpg", b"not-a-jpeg")
    codes = [item.code for item in result.findings]
    assert codes == ["CONTENT_SIGNATURE_MISMATCH"]
