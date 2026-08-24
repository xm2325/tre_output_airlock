from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ReceivedQueueMessage:
    message_id: str
    receipt_handle: str
    body: str


class QueueTransport(Protocol):
    def send(self, body: str) -> str: ...

    def receive(
        self,
        *,
        max_messages: int,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> list[ReceivedQueueMessage]: ...

    def change_visibility(self, receipt_handle: str, visibility_timeout_seconds: int) -> None: ...

    def delete(self, receipt_handle: str) -> None: ...


class AwsSqsTransport:
    def __init__(
        self,
        *,
        queue_url: str,
        region_name: str,
        endpoint_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not queue_url.strip():
            raise ValueError("AIRLOCK_SCAN_QUEUE_URL must be configured for SQS transport")
        self.queue_url = queue_url
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - deployment dependency guard
                raise RuntimeError("boto3 is required for AWS SQS transport") from exc
            client = boto3.client(
                "sqs",
                region_name=region_name,
                endpoint_url=endpoint_url,
            )
        self.client = client

    def send(self, body: str) -> str:
        response = self.client.send_message(QueueUrl=self.queue_url, MessageBody=body)
        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id:
            raise RuntimeError("SQS send_message returned no MessageId")
        return message_id

    def receive(
        self,
        *,
        max_messages: int,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> list[ReceivedQueueMessage]:
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
            VisibilityTimeout=visibility_timeout_seconds,
        )
        messages = response.get("Messages", [])
        result: list[ReceivedQueueMessage] = []
        for item in messages:
            message_id = item.get("MessageId")
            receipt_handle = item.get("ReceiptHandle")
            body = item.get("Body")
            values = (message_id, receipt_handle, body)
            if not all(isinstance(value, str) and value for value in values):
                raise RuntimeError("SQS receive_message returned a malformed message")
            result.append(
                ReceivedQueueMessage(
                    message_id=message_id,
                    receipt_handle=receipt_handle,
                    body=body,
                )
            )
        return result

    def change_visibility(self, receipt_handle: str, visibility_timeout_seconds: int) -> None:
        self.client.change_message_visibility(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=visibility_timeout_seconds,
        )

    def delete(self, receipt_handle: str) -> None:
        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
