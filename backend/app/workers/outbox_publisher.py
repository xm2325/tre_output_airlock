from __future__ import annotations

import time

from app.core.async_scan import load_async_scan_settings
from app.db import SessionLocal
from app.services.outbox_publisher import PublishBatchResult, publish_outbox_batch
from app.services.sqs_transport import AwsSqsTransport, QueueTransport


def run_publisher_once(transport: QueueTransport) -> PublishBatchResult:
    settings = load_async_scan_settings()
    with SessionLocal() as db:
        return publish_outbox_batch(db, transport, settings)


def main() -> None:
    settings = load_async_scan_settings()
    transport = AwsSqsTransport(
        queue_url=settings.queue_url,
        region_name=settings.aws_region,
        endpoint_url=settings.endpoint_url,
    )
    while True:
        result = run_publisher_once(transport)
        if result.claimed == 0:
            time.sleep(1.0)


if __name__ == "__main__":
    main()
