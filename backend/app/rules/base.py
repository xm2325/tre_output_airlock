from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass(frozen=True)
class FindingResult:
    code: str
    severity: Severity
    message: str
    evidence: str | None = None


@dataclass(frozen=True)
class FileContext:
    path: Path
    filename: str
    content_type: str
    size_bytes: int


class Rule(Protocol):
    def evaluate(self, context: FileContext) -> list[FindingResult]: ...
