from __future__ import annotations

import hashlib
import json

IDEMPOTENCY_FINGERPRINT_VERSION = "submission-create-v1"


def idempotency_scope_key(actor_name: str, raw_key: str) -> str:
    material = f"{actor_name}\0{raw_key}".encode()
    return hashlib.sha256(material).hexdigest()


def submission_request_fingerprint(
    *,
    project_code: str,
    output_type: str,
    output_description: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
) -> str:
    payload = {
        "contract": IDEMPOTENCY_FINGERPRINT_VERSION,
        "content_type": content_type,
        "filename": filename,
        "output_description": output_description,
        "output_type": output_type,
        "project_code": project_code,
        "sha256": sha256,
        "size_bytes": size_bytes,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
