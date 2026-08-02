import asyncio
import uuid
import pytest
from src.config import Settings
from src.main import QRScannerEngine
from tests.test_simulator import QRScannerHardwareSimulator, AWSIoTBrokerSimulator


@pytest.mark.asyncio
async def test_end_to_end_qr_scanning_flow(monkeypatch):
    """Integrations test: Verifies complete flow from QR scan input to AWS IoT published payload."""
    settings = Settings(
        AWS_IOT_ENDPOINT="mock-ats.iot.eu-central-1.amazonaws.com",
        AWS_IOT_CLIENT_ID="rpi-integration-test-01",
        AWS_IOT_TOPIC="scanners/qr/integration_test",
        MOCK_SERIAL=False,  # We will manually feed scans into the callback
        MOCK_AWS=True,
        LOG_LEVEL="DEBUG"
    )

    broker_simulator = AWSIoTBrokerSimulator()
    engine = QRScannerEngine(settings=settings)

    # Start engine
    await engine.start()

    # Define test QR codes to inject
    test_scans = [
        "https://crossboxgym.pl/checkin/member/987654",
        '{"user_id": 777, "pass_type": "VIP_MONTHLY"}',
        "Zażółć gęślą jaźń 123 !@#$",
        "SIMPLE_TEXT_QR"
    ]

    # Inject test scans into engine's listener callback
    for raw_qr in test_scans:
        await engine._handle_scanned_qr(raw_qr)

    # Wait for queue worker to process all items
    await asyncio.sleep(0.5)

    # Verify published messages in publisher history
    history = engine.publisher.published_messages_history
    assert len(history) == len(test_scans)

    for idx, expected_raw in enumerate(test_scans):
        msg = history[idx]
        assert "event_id" in msg
        assert uuid.UUID(msg["event_id"])  # Valid UUID4
        assert msg["client_id"] == "rpi-integration-test-01"
        assert isinstance(msg["timestamp"], int)
        assert msg["payload"]["raw_data"] == expected_raw
        assert msg["payload"]["encoding"] == "utf-8"

    # Stop engine cleanly
    await engine.stop()


@pytest.mark.asyncio
async def test_simulator_hardware_to_broker_integration():
    """Integrates Hardware Simulator with QRScannerEngine and AWS Broker Simulator."""
    settings = Settings(
        AWS_IOT_ENDPOINT="mock-ats.iot.eu-central-1.amazonaws.com",
        AWS_IOT_CLIENT_ID="simulator-client-99",
        AWS_IOT_TOPIC="gym/scanners/entry",
        MOCK_SERIAL=False,
        MOCK_AWS=True
    )

    hardware_sim = QRScannerHardwareSimulator()
    broker_sim = AWSIoTBrokerSimulator()
    engine = QRScannerEngine(settings=settings)

    await engine.start()

    # Enqueue 3 raw hardware lines into simulator
    hardware_sim.queue_scan("https://crossboxgym.pl/entry/scan1", line_ending="\r\n")
    hardware_sim.queue_scan("PASS_CODE_ABC_123", line_ending="\n")
    hardware_sim.queue_scan("{\"ticket\": 404}", line_ending="\r\n")

    # Read hardware lines and pass to engine
    while True:
        line_bytes = hardware_sim.read_line()
        if not line_bytes:
            break
        cleaned = engine.listener.clean_payload(line_bytes)
        await engine._handle_scanned_qr(cleaned)

    # Wait for worker processing
    await asyncio.sleep(0.5)

    # Pass history to broker simulator for validation
    for msg in engine.publisher.published_messages_history:
        broker_sim.receive_message(settings.AWS_IOT_TOPIC, msg)

    assert len(broker_sim.received_messages) == 3
    assert broker_sim.received_messages[0]["payload"]["payload"]["raw_data"] == "https://crossboxgym.pl/entry/scan1"
    assert broker_sim.received_messages[1]["payload"]["payload"]["raw_data"] == "PASS_CODE_ABC_123"
    assert broker_sim.received_messages[2]["payload"]["payload"]["raw_data"] == "{\"ticket\": 404}"

    await engine.stop()
