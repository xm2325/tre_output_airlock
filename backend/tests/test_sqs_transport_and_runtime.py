from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from app.core.async_scan import load_async_scan_settings
from app.db import SessionLocal
from app.models import OutboxEvent, Submission
from app.services.scan_jobs import enqueue_scan
from app.services.sqs_transport import AwsSqsTransport
from app.workers.outbox_publisher import run_publisher_once


class FakeSqsClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.deleted: list[dict[str, str]] = []
        self.receive_response: dict[str, Any] = {"Messages": []}
        self.send_response: dict[str, Any] = {"MessageId": "message-1"}

    def send_message(self, **kwargs: str) -> dict[str, Any]:
        self.sent.append(kwargs)
        return self.send_response

    def receive_message(self, **kwargs: Any) -> dict[str, Any]:
        self.receive_kwargs = kwargs
        return self.receive_response

    def delete_message(self, **kwargs: str) -> None:
        self.deleted.append(kwargs)


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, body: str) -> str:
        self.sent.append(body)
        return "publisher-message-1"

    def receive(
        self,
        *,
        max_messages: int,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> list[Any]:
        del max_messages, wait_seconds, visibility_timeout_seconds
        return []

    def delete(self, receipt_handle: str) -> None:
        del receipt_handle


def _submission() -> Submission:
    return Submission(
        id="runtime-queued-submission",
        project_code="RUNTIME-CI",
        output_type="TABLE",
        output_description="Synthetic runtime boundary contract for queue publishing.",
        filename="runtime.csv",
        content_type="text/csv",
        size_bytes=10,
        sha256="a" * 64,
        idempotency_key=None,
        status="QUARANTINED",
        automated_decision="ALLOW",
        final_decision=None,
        risk_score=0.0,
        policy_version="test-policy",
        submitted_by="runtime-researcher",
        row_version=1,
    )


def test_async_settings_defaults_and_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AIRLOCK_SCAN_MODE",
        "AIRLOCK_SCAN_QUEUE_URL",
        "AIRLOCK_AWS_REGION",
        "AIRLOCK_SQS_ENDPOINT_URL",
        "AIRLOCK_OUTBOX_BATCH_SIZE",
        "AIRLOCK_OUTBOX_CLAIM_TTL_SECONDS",
        "AIRLOCK_SCAN_WORKER_CLAIM_TTL_SECONDS",
        "AIRLOCK_SQS_WAIT_TIME_SECONDS",
        "AIRLOCK_SQS_VISIBILITY_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_async_scan_settings()
    assert settings.mode == "synchronous"
    assert settings.aws_region == "eu-west-2"
    assert settings.endpoint_url is None
    assert settings.outbox_batch_size == 10

    monkeypatch.setenv("AIRLOCK_SCAN_MODE", "invalid")
    with pytest.raises(ValueError, match="AIRLOCK_SCAN_MODE"):
        load_async_scan_settings()

    monkeypatch.setenv("AIRLOCK_SCAN_MODE", "queued")
    monkeypatch.setenv("AIRLOCK_OUTBOX_BATCH_SIZE", "not-an-int")
    with pytest.raises(ValueError, match="AIRLOCK_OUTBOX_BATCH_SIZE must be an integer"):
        load_async_scan_settings()

    monkeypatch.setenv("AIRLOCK_OUTBOX_BATCH_SIZE", "101")
    with pytest.raises(ValueError, match="between 1 and 100"):
        load_async_scan_settings()


def test_sqs_transport_builds_client_and_round_trips_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSqsClient()
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: fake))

    transport = AwsSqsTransport(
        queue_url="https://sqs.example/scan",
        region_name="eu-west-2",
        endpoint_url="http://sqs-compatible:5000",
    )
    assert transport.send('{"job":"one"}') == "message-1"
    assert fake.sent == [
        {"QueueUrl": "https://sqs.example/scan", "MessageBody": '{"job":"one"}'}
    ]

    fake.receive_response = {
        "Messages": [
            {
                "MessageId": "received-1",
                "ReceiptHandle": "receipt-1",
                "Body": '{"job":"one"}',
            }
        ]
    }
    messages = transport.receive(
        max_messages=3,
        wait_seconds=4,
        visibility_timeout_seconds=30,
    )
    assert len(messages) == 1
    assert messages[0].message_id == "received-1"
    assert messages[0].receipt_handle == "receipt-1"
    assert messages[0].body == '{"job":"one"}'
    assert fake.receive_kwargs == {
        "QueueUrl": "https://sqs.example/scan",
        "MaxNumberOfMessages": 3,
        "WaitTimeSeconds": 4,
        "VisibilityTimeout": 30,
    }

    transport.delete("receipt-1")
    assert fake.deleted == [
        {"QueueUrl": "https://sqs.example/scan", "ReceiptHandle": "receipt-1"}
    ]


def test_sqs_transport_rejects_invalid_contracts() -> None:
    fake = FakeSqsClient()
    with pytest.raises(ValueError, match="AIRLOCK_SCAN_QUEUE_URL"):
        AwsSqsTransport(queue_url=" ", region_name="eu-west-2", client=fake)

    transport = AwsSqsTransport(
        queue_url="https://sqs.example/scan",
        region_name="eu-west-2",
        client=fake,
    )
    fake.send_response = {}
    with pytest.raises(RuntimeError, match="no MessageId"):
        transport.send("payload")

    fake.receive_response = {
        "Messages": [{"MessageId": "bad", "ReceiptHandle": "receipt", "Body": None}]
    }
    with pytest.raises(RuntimeError, match="malformed message"):
        transport.receive(max_messages=1, wait_seconds=0, visibility_timeout_seconds=10)


def test_independent_publisher_runner_publishes_committed_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIRLOCK_SCAN_MODE", "queued")
    monkeypatch.setenv("AIRLOCK_SCAN_QUEUE_URL", "https://sqs.example/scan")
    transport = FakeTransport()

    with SessionLocal() as db:
        submission = _submission()
        db.add(submission)
        db.flush()
        enqueue_scan(db, submission, request_id="publisher-runner-test")
        db.commit()

    result = run_publisher_once(transport)
    assert result.claimed == 1
    assert result.published == 1
    assert result.failed == 0
    assert len(transport.sent) == 1

    with SessionLocal() as db:
        event = db.scalar(select(OutboxEvent))
        assert event is not None
        assert event.status == "PUBLISHED"
