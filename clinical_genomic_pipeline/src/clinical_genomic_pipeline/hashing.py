"""Hashing and deterministic pseudonymisation utilities."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for a file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    """Return the SHA-256 digest for UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pseudonymise(identifier: str, secret: str, prefix: str = "P") -> str:
    """Create a stable, non-reversible identifier for this demonstration."""
    if not identifier:
        raise ValueError("identifier must not be empty")
    if len(secret) < 16:
        raise ValueError("pseudonymisation secret must contain at least 16 characters")
    digest = hmac.new(secret.encode("utf-8"), identifier.encode("utf-8"), hashlib.sha256)
    return f"{prefix}-{digest.hexdigest()[:20]}"


def deterministic_date_shift_days(identifier: str, secret: str, limit: int = 30) -> int:
    """Return a stable date shift in the inclusive range [-limit, limit]."""
    digest = hmac.new(secret.encode("utf-8"), identifier.encode("utf-8"), hashlib.sha256)
    integer = int.from_bytes(digest.digest()[:4], "big")
    return (integer % (2 * limit + 1)) - limit
