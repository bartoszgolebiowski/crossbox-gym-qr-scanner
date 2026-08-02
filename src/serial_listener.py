import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Optional
import serial

logger = logging.getLogger(__name__)

MOCK_QR_SAMPLES = [
    "https://crossboxgym.pl/checkin/member/12345",
    "https://crossboxgym.pl/checkin/member/67890",
    "CROSSBOX-PASS-9988776655",
    '{"user_id": 99, "ticket_code": "GYM-2026-XYZ"}',
    "https://example.com/qr-code-content",
]


class SerialScannerListener:
    """Monitors serial port for QR scanner output with auto-reconnect and mock support."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        on_scan_callback: Callable[[str], Awaitable[None]],
        mock_mode: bool = False,
        mock_interval: float = 3.0,
        reconnect_delay: float = 2.0,
    ):
        self.port = port
        self.baudrate = baudrate
        self.on_scan_callback = on_scan_callback
        self.mock_mode = mock_mode
        self.mock_interval = mock_interval
        self.reconnect_delay = reconnect_delay
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts the serial reading loop task."""
        if self._running:
            logger.warning("SerialScannerListener is already running.")
            return

        self._running = True
        if self.mock_mode:
            logger.info("Starting SerialScannerListener in MOCK mode (interval=%.1fs).", self.mock_interval)
            self._task = asyncio.create_task(self._run_mock_loop())
        else:
            logger.info("Starting SerialScannerListener on port '%s' (baudrate=%d).", self.port, self.baudrate)
            self._task = asyncio.create_task(self._run_serial_loop())

    async def stop(self) -> None:
        """Stops the serial reading loop task gracefully."""
        logger.info("Stopping SerialScannerListener...")
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SerialScannerListener stopped.")

    def clean_payload(self, raw_bytes: bytes) -> str:
        """Cleans carriage returns, line feeds, and trailing whitespace from decoded UTF-8 string."""
        text = raw_bytes.decode("utf-8", errors="replace")
        cleaned = text.strip("\r\n \t")
        return cleaned

    async def _run_serial_loop(self) -> None:
        """Continuously reads from the physical serial port with auto-reconnect logic."""
        while self._running:
            ser: Optional[serial.Serial] = None
            try:
                logger.info("Connecting to serial port '%s'...", self.port)
                # Open port in non-blocking / short timeout mode
                ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
                logger.info("Successfully connected to serial port '%s'. Listening for scans...", self.port)

                loop = asyncio.get_running_loop()

                while self._running:
                    # Read line off-thread to prevent blocking event loop
                    line_bytes = await loop.run_in_executor(None, ser.readline)
                    if line_bytes:
                        cleaned_data = self.clean_payload(line_bytes)
                        if cleaned_data:
                            logger.debug("Scanned raw data: %s", cleaned_data)
                            await self.on_scan_callback(cleaned_data)
                    await asyncio.sleep(0.05)

            except serial.SerialException as exc:
                logger.error("Serial port error on '%s': %s. Reconnecting in %.1fs...", self.port, exc, self.reconnect_delay)
            except Exception as exc:
                logger.error("Unexpected error reading serial port: %s. Reconnecting in %.1fs...", exc, self.reconnect_delay)
            finally:
                if ser and ser.is_open:
                    try:
                        ser.close()
                    except Exception:
                        pass

            if self._running:
                await asyncio.sleep(self.reconnect_delay)

    async def _run_mock_loop(self) -> None:
        """Generates simulated QR scan events at configurable intervals."""
        while self._running:
            await asyncio.sleep(self.mock_interval)
            if not self._running:
                break
            mock_data = random.choice(MOCK_QR_SAMPLES)
            logger.info("[MOCK SCANNER] Emulating scan event: %s", mock_data)
            await self.on_scan_callback(mock_data)
