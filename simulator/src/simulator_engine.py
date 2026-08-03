import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional
from src.aws_publisher import SimulatorAWSPublisher
from src.config import SimulatorSettings, get_simulator_settings

from src.aws_publisher import BaseIoTPublisher

logger = logging.getLogger("SimulatorEngine")

DEFAULT_MOCK_QR_PRESETS = [
    "https://crossboxgym.pl/checkin/member/12345",
    "https://crossboxgym.pl/checkin/member/67890",
    "CROSSBOX-PASS-9988776655",
    '{"user_id": 99, "ticket_code": "GYM-2026-XYZ"}',
    "https://crossboxgym.pl/pass/vip-771122",
    "CROSSBOX-GUEST-001299"
]


class SimulatorEngine:
    """Core simulator engine orchestrating QR trigger events and AWS IoT publishing."""

    def __init__(
        self,
        settings: Optional[SimulatorSettings] = None,
        publisher: Optional[BaseIoTPublisher] = None
    ):
        self.settings = settings or get_simulator_settings()
        self.publisher = publisher or SimulatorAWSPublisher(self.settings)
        self.auto_scan_active = False
        self.auto_scan_interval = 3.0
        self._auto_scan_task: Optional[asyncio.Task] = None
        self.total_scans_count = 0
        self.last_scan_payload: Optional[Dict[str, Any]] = None

    async def start(self) -> None:
        """Starts the simulator engine and initializes AWS connection."""
        logger.info("Starting Simulator Engine...")
        await self.publisher.connect()

    async def stop(self) -> None:
        """Stops background tasks and disconnects AWS publisher."""
        logger.info("Stopping Simulator Engine...")
        await self.stop_auto_scan()
        await self.publisher.disconnect()

    async def trigger_scan(self, qr_data: str) -> Optional[Dict[str, Any]]:
        """Triggers a single simulated QR scan event and publishes to AWS IoT."""
        logger.info("[TRIGGER SCAN] Emulating scan event for string: '%s'", qr_data)
        res = await self.publisher.publish_scan(qr_data)
        if res:
            self.total_scans_count += 1
            self.last_scan_payload = res
        return res

    async def start_auto_scan(self, interval_seconds: float = 3.0) -> bool:
        """Starts background loop that generates random QR scans periodically."""
        if self.auto_scan_active:
            logger.warning("Auto-scan is already active.")
            return False

        self.auto_scan_interval = max(0.5, interval_seconds)
        self.auto_scan_active = True
        self._auto_scan_task = asyncio.create_task(self._auto_scan_loop())
        logger.info("Auto-scan simulation started with interval %.1fs.", self.auto_scan_interval)
        return True

    async def stop_auto_scan(self) -> bool:
        """Stops the background auto-scan generator."""
        if not self.auto_scan_active:
            return False

        self.auto_scan_active = False
        if self._auto_scan_task and not self._auto_scan_task.done():
            self._auto_scan_task.cancel()
            try:
                await self._auto_scan_task
            except asyncio.CancelledError:
                pass
        logger.info("Auto-scan simulation stopped.")
        return True

    async def _auto_scan_loop(self) -> None:
        """Loop function for periodic auto-scanning."""
        while self.auto_scan_active:
            try:
                await asyncio.sleep(self.auto_scan_interval)
                if not self.auto_scan_active:
                    break
                random_qr = random.choice(DEFAULT_MOCK_QR_PRESETS)
                logger.info("[AUTO-SCAN] Auto-triggering scan for: %s", random_qr)
                await self.trigger_scan(random_qr)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in auto-scan loop: %s", exc)

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic status of the simulator engine."""
        return {
            "status": "online",
            "aws_connected": self.publisher.is_connected,
            "aws_iot_endpoint": self.settings.AWS_IOT_ENDPOINT,
            "aws_iot_client_id": self.settings.AWS_IOT_CLIENT_ID,
            "aws_iot_topic": self.settings.AWS_IOT_TOPIC,
            "aws_secret_name": self.settings.AWS_SECRET_NAME,
            "aws_region": self.settings.AWS_REGION,
            "auto_scan_active": self.auto_scan_active,
            "auto_scan_interval": self.auto_scan_interval,
            "total_scans_count": self.total_scans_count,
            "last_scan": self.last_scan_payload
        }
