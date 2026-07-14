from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


class FileTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    path: Path
    size_bytes: int
    sha256: str


def quarantined_path(submission_id: str, filename: str) -> Path:
    extension = Path(filename).suffix.lower()
    return settings.quarantine_dir / f"{submission_id}{extension}"


async def store_quarantined_file(upload: UploadFile, submission_id: str) -> StoredFile:
    settings.quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantined_path(submission_id, upload.filename or "upload.bin")
    digest = hashlib.sha256()
    size = 0

    try:
        with target.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_file_size_bytes:
                    raise FileTooLargeError(
                        f"File exceeds the {settings.max_file_size_mb} MB demonstration limit."
                    )
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredFile(path=target, size_bytes=size, sha256=digest.hexdigest())
