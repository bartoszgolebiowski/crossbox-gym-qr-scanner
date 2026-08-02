import asyncio
import pytest
from src.serial_listener import SerialScannerListener


def test_clean_payload_stripping():
    """Verifies that clean_payload strips carriage returns, newlines, and trailing spaces."""
    listener = SerialScannerListener(
        port="/dev/ttyACM0",
        baudrate=9600,
        on_scan_callback=lambda x: None
    )

    raw_1 = b"https://example.com/qr\r\n"
    assert listener.clean_payload(raw_1) == "https://example.com/qr"

    raw_2 = b"\r\n\t  CROSSBOX-12345  \r\n"
    assert listener.clean_payload(raw_2) == "CROSSBOX-12345"

    raw_utf8 = "Zażółć gęślą jaźń\r\n".encode("utf-8")
    assert listener.clean_payload(raw_utf8) == "Zażółć gęślą jaźń"


@pytest.mark.asyncio
async def test_mock_serial_loop_emission():
    """Verifies that mock serial loop emits events to the callback."""
    scanned_results = []

    async def callback(data: str):
        scanned_results.append(data)

    listener = SerialScannerListener(
        port="/dev/ttyACM0",
        baudrate=9600,
        on_scan_callback=callback,
        mock_mode=True,
        mock_interval=0.1
    )

    await listener.start()
    await asyncio.sleep(0.35)
    await listener.stop()

    assert len(scanned_results) >= 2
    for item in scanned_results:
        assert isinstance(item, str)
        assert len(item) > 0
