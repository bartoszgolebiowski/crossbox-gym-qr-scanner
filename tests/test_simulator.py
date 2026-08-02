import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger("QRSimulator")


class QRScannerHardwareSimulator:
    """Simulates physical USB QR Scanner hardware emitting raw bytes over serial stream."""

    def __init__(self):
        self.buffer: List[bytes] = []

    def queue_scan(self, qr_text: str, line_ending: str = "\r\n") -> None:
        """Enqueues a raw text scan payload formatted with line endings."""
        raw_bytes = f"{qr_text}{line_ending}".encode("utf-8")
        self.buffer.append(raw_bytes)

    def read_line(self) -> bytes:
        """Simulates serial readline operation."""
        if self.buffer:
            return self.buffer.pop(0)
        return b""


class AWSIoTBrokerSimulator:
    """Simulates AWS IoT Core Broker receiving published MQTT topics and validating payloads."""

    def __init__(self):
        self.received_messages: List[Dict[str, Any]] = []

    def receive_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """Records incoming published MQTT message."""
        logger.info("Broker received message on topic '%s': %s", topic, payload)
        self.received_messages.append({"topic": topic, "payload": payload})

    def clear(self) -> None:
        self.received_messages.clear()
