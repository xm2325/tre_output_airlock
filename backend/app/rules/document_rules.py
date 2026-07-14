from __future__ import annotations

from PIL import ExifTags, Image
from pypdf import PdfReader

from app.rules.base import FileContext, FindingResult
from app.rules.common import scan_text


class TextRule:
    def evaluate(self, context: FileContext) -> list[FindingResult]:
        if context.path.suffix.lower() != ".txt":
            return []
        try:
            text = context.path.read_text(encoding="utf-8", errors="replace")[:1_000_000]
        except OSError as exc:
            return [
                FindingResult(
                    code="TEXT_READ_ERROR",
                    severity="HIGH",
                    message="The text file could not be read reliably.",
                    evidence=f"error_type={type(exc).__name__}",
                )
            ]
        return scan_text(text, "text_file")


class PdfRule:
    def evaluate(self, context: FileContext) -> list[FindingResult]:
        if context.path.suffix.lower() != ".pdf":
            return []
        findings: list[FindingResult] = []
        try:
            # FileSignatureRule already creates the blocking finding. Avoid sending
            # clearly invalid bytes into pypdf, which would add duplicate findings
            # and noisy parser output without improving the decision.
            if not context.path.read_bytes()[:5].startswith(b"%PDF-"):
                return []
            reader = PdfReader(str(context.path))
            text_parts: list[str] = []
            for page in reader.pages[:20]:
                text_parts.append(page.extract_text() or "")
            findings.extend(scan_text("\n".join(text_parts)[:1_000_000], "pdf_text"))
            metadata = reader.metadata
            if metadata and any(metadata.values()):
                findings.append(
                    FindingResult(
                        code="PDF_METADATA_PRESENT",
                        severity="LOW",
                        message="PDF metadata is present and should be checked before release.",
                        evidence="metadata_values_redacted=true",
                    )
                )
        except Exception as exc:  # pypdf raises several parser-specific exceptions
            findings.append(
                FindingResult(
                    code="PDF_PARSE_ERROR",
                    severity="HIGH",
                    message="The PDF could not be parsed reliably and requires manual review.",
                    evidence=f"error_type={type(exc).__name__}",
                )
            )
        return findings


class ImageMetadataRule:
    def evaluate(self, context: FileContext) -> list[FindingResult]:
        if context.path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            return []
        findings: list[FindingResult] = []
        try:
            prefix = context.path.read_bytes()[:8]
            suffix = context.path.suffix.lower()
            valid_signature = (
                suffix == ".png" and prefix.startswith(b"\x89PNG\r\n\x1a\n")
            ) or (suffix in {".jpg", ".jpeg"} and prefix.startswith(b"\xff\xd8\xff"))
            if not valid_signature:
                return []
            with Image.open(context.path) as image:
                exif = image.getexif()
                if exif:
                    names = {ExifTags.TAGS.get(key, str(key)) for key in exif}
                    if "GPSInfo" in names:
                        findings.append(
                            FindingResult(
                                code="IMAGE_GPS_METADATA",
                                severity="CRITICAL",
                                message="Image metadata contains location information.",
                                evidence="gps_values_redacted=true",
                            )
                        )
                    else:
                        findings.append(
                            FindingResult(
                                code="IMAGE_METADATA_PRESENT",
                                severity="LOW",
                                message=(
                                    "Image metadata is present and should be removed or checked."
                                ),
                                evidence=f"metadata_fields={len(names)}; values_redacted=true",
                            )
                        )
        except Exception as exc:
            findings.append(
                FindingResult(
                    code="IMAGE_PARSE_ERROR",
                    severity="HIGH",
                    message="The image could not be parsed reliably and requires manual review.",
                    evidence=f"error_type={type(exc).__name__}",
                )
            )
        return findings
