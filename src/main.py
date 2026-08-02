import asyncio
import logging
import signal
import sys
from typing import Optional

from src.aws_publisher import AWSIoTPublisher
from src.config import Settings, get_settings
from src.serial_listener import SerialScannerListener

logger = logging.getLogger("EngineMain")


class QRScannerEngine:
    """Orchestrates serial port listener, queue worker, and AWS IoT publisher."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._setup_logging()
        self.publisher = AWSIoTPublisher(self.settings)
        self.scan_queue: asyncio.Queue[str] = asyncio.Queue()
        self.listener = SerialScannerListener(
            port=self.settings.SERIAL_PORT,
            baudrate=self.settings.SERIAL_BAUDRATE,
            on_scan_callback=self._handle_scanned_qr,
            mock_mode=self.settings.MOCK_SERIAL,
            mock_interval=self.settings.MOCK_SERIAL_INTERVAL,
        )
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    def _setup_logging(self) -> None:
        """Configures root logger level and format."""
        log_level = getattr(logging, self.settings.LOG_LEVEL.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    async def _handle_scanned_qr(self, raw_data: str) -> None:
        """Callback invoked whenever a QR code is read from serial stream."""
        logger.info("QR Code captured: '%s'. Adding to queue...", raw_data)
        await self.scan_queue.put(raw_data)

    async def _queue_worker(self) -> None:
        """Worker task processing items from the scan queue."""
        logger.info("Queue processing worker started.")
        while self._running:
            try:
                # Wait for items with short timeout to check running flag
                raw_data = await asyncio.wait_for(self.scan_queue.get(), timeout=1.0)
                logger.info("Processing scan item from queue: '%s'", raw_data)
                result = await self.publisher.publish_scan(raw_data)
                if result:
                    logger.info("Published scan event ID: %s", result.get("event_id"))
                else:
                    logger.warning("Failed to publish scan event for: %s", raw_data)
                self.scan_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in queue worker: %s", exc)

    async def start(self) -> None:
        """Starts the engine, AWS connection, serial listener, and queue worker."""
        logger.info("Starting QRScannerEngine...")
        self._running = True

        # Connect AWS IoT Publisher
        await self.publisher.connect()

        # Start Queue Worker
        self._worker_task = asyncio.create_task(self._queue_worker())

        # Start Serial Listener
        await self.listener.start()
        logger.info("QRScannerEngine is fully operational.")

    async def stop(self) -> None:
        """Stops all components gracefully."""
        logger.info("Stopping QRScannerEngine...")
        self._running = False

        # Stop serial listener
        await self.listener.stop()

        # Stop worker task
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        # Disconnect AWS IoT publisher
        await self.publisher.disconnect()
        logger.info("QRScannerEngine stopped.")


async def main_async() -> None:
    """Entry point for running engine with signal handling."""
    engine = QRScannerEngine()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Received termination signal.")
        stop_event.set()

    # Register OS signal handlers if supported (Unix & Windows compat)
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    await engine.start()

    try:
        if sys.platform == "win32":
            # On Windows, keep running until KeyboardInterrupt or cancellation
            while not stop_event.is_set():
                await asyncio.sleep(0.5)
        else:
            await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await engine.stop()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Exiting engine gracefully...")


if __name__ == "__main__":
    main()
