import asyncio
import uuid
import pytest
from src.aws_publisher import StubIoTPublisher
from src.config import Settings
from src.main import QRScannerEngine
from tests.test_simulator import QRScannerHardwareSimulator, AWSIoTBrokerSimulator


@pytest.mark.asyncio
async def test_end_to_end_qr_scanning_flow():
    """Integrations test: Verifies complete flow from QR scan input to AWS IoT published payload using StubIoTPublisher."""
    settings = Settings(
        AWS_IOT_ENDPOINT="test-ats.iot.eu-central-1.amazonaws.com",
        AWS_IOT_CLIENT_ID="crossbox-integration-test-01",
        AWS_IOT_TOPIC="gym/scanners/crossbox-qr-scanner-01/scan",
        MOCK_SERIAL=False,
        LOG_LEVEL="DEBUG"
    )

    stub_publisher = StubIoTPublisher(
        client_id=settings.AWS_IOT_CLIENT_ID,
        topic=settings.AWS_IOT_TOPIC
    )
    engine = QRScannerEngine(settings=settings, publisher=stub_publisher)

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

    # Verify published scan messages in publisher history (filter out heartbeats)
    scan_history = [
        msg for msg in stub_publisher.published_messages_history
        if "event_id" in msg
    ]
    assert len(scan_history) == len(test_scans)

    for idx, expected_raw in enumerate(test_scans):
        msg = scan_history[idx]
        assert "event_id" in msg
        assert uuid.UUID(msg["event_id"])  # Valid UUID4
        assert msg["client_id"] == "crossbox-integration-test-01"
        assert isinstance(msg["timestamp"], int)
        assert msg["payload"]["raw_data"] == expected_raw
        assert msg["payload"]["encoding"] == "utf-8"

    # Stop engine cleanly
    await engine.stop()


@pytest.mark.asyncio
async def test_simulator_hardware_to_broker_integration():
    """Integrates Hardware Simulator with QRScannerEngine and AWS Broker Simulator."""
    settings = Settings(
        AWS_IOT_ENDPOINT="test-ats.iot.eu-central-1.amazonaws.com",
        AWS_IOT_CLIENT_ID="simulator-client-99",
        AWS_IOT_TOPIC="gym/scanners/crossbox-qr-scanner-01/scan",
        MOCK_SERIAL=False
    )

    stub_publisher = StubIoTPublisher(
        client_id=settings.AWS_IOT_CLIENT_ID,
        topic=settings.AWS_IOT_TOPIC
    )
    hardware_sim = QRScannerHardwareSimulator()
    broker_sim = AWSIoTBrokerSimulator()
    engine = QRScannerEngine(settings=settings, publisher=stub_publisher)

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

    # Pass scan history to broker simulator for validation (filter out heartbeats)
    for msg in stub_publisher.published_messages_history:
        if "event_id" in msg:
            broker_sim.receive_message(settings.AWS_IOT_TOPIC, msg)

    assert len(broker_sim.received_messages) == 3
    assert broker_sim.received_messages[0]["payload"]["payload"]["raw_data"] == "https://crossboxgym.pl/entry/scan1"
    assert broker_sim.received_messages[1]["payload"]["payload"]["raw_data"] == "PASS_CODE_ABC_123"
    assert broker_sim.received_messages[2]["payload"]["payload"]["raw_data"] == "{\"ticket\": 404}"

    await engine.stop()


@pytest.mark.asyncio
async def test_engine_publishes_heartbeat():
    """Verifies that QRScannerEngine publishes periodic heartbeat messages."""
    settings = Settings(
        AWS_IOT_ENDPOINT="test-ats.iot.eu-central-1.amazonaws.com",
        AWS_IOT_CLIENT_ID="crossbox-heartbeat-test-01",
        AWS_IOT_HEARTBEAT_INTERVAL_SECONDS=1,
        AWS_IOT_HEARTBEAT_TOPIC="gym/devices/crossbox-heartbeat-test-01/heartbeat",
        MOCK_SERIAL=True,
        LOG_LEVEL="DEBUG",
    )
    pub = StubIoTPublisher(client_id=settings.AWS_IOT_CLIENT_ID, topic=settings.AWS_IOT_TOPIC)
    engine = QRScannerEngine(settings=settings, publisher=pub)

    await engine.start()
    await asyncio.sleep(1.5)
    await engine.stop()

    heartbeat_messages = [
        msg for msg in pub.published_messages_history
        if msg.get("topic") == settings.AWS_IOT_HEARTBEAT_TOPIC
    ]
    assert len(heartbeat_messages) >= 1
    heartbeat = heartbeat_messages[0]
    assert heartbeat["thingName"] == settings.AWS_IOT_CLIENT_ID
    assert heartbeat["deviceType"] == "HDWR-HD360-QR-Scanner"
    assert heartbeat["status"] == "online"
    assert "timestamp" in heartbeat
    assert "uptime_ms" in heartbeat
    assert heartbeat["version"] == "1.0.0"
