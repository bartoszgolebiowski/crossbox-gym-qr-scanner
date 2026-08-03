import uuid
import pytest
from src.aws_publisher import AWSIoTPublisher, StubIoTPublisher
from src.config import Settings


def test_build_payload_schema():
    """Verifies that build_payload generates a payload matching the PRD spec."""
    settings = Settings(
        AWS_IOT_ENDPOINT="test.iot.amazonaws.com",
        AWS_IOT_CLIENT_ID="crossbox-test-client-01"
    )
    publisher = AWSIoTPublisher(settings)

    raw_qr = "https://crossboxgym.pl/checkin/member/999"
    payload = publisher.build_payload(raw_qr)

    # Check root keys
    assert "event_id" in payload
    assert "client_id" in payload
    assert "timestamp" in payload
    assert "payload" in payload

    # Validate types and values
    assert uuid.UUID(payload["event_id"])  # must be valid UUID4
    assert payload["client_id"] == "crossbox-test-client-01"
    assert isinstance(payload["timestamp"], int)
    assert payload["payload"]["raw_data"] == raw_qr
    assert payload["payload"]["encoding"] == "utf-8"


@pytest.mark.asyncio
async def test_stub_iot_publisher():
    """Verifies that publishing via StubIoTPublisher records messages in history."""
    publisher = StubIoTPublisher(client_id="stub-client", topic="gym/scanners/stub/scan")
    connected = await publisher.connect()
    assert connected is True
    assert publisher.is_connected is True

    result = await publisher.publish_scan("TEST_QR_CODE_CONTENT")
    assert result is not None
    assert result["payload"]["raw_data"] == "TEST_QR_CODE_CONTENT"
    assert len(publisher.published_messages_history) == 1

    await publisher.disconnect()
    assert publisher.is_connected is False
