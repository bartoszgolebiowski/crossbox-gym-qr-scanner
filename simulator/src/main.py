import asyncio
import logging
import sys
import uvicorn
from contextlib import asynccontextmanager
from src.api import create_app
from src.config import get_simulator_settings
from src.simulator_engine import SimulatorEngine

logger = logging.getLogger("SimulatorMain")


def main() -> None:
    settings = get_simulator_settings()

    # Configure logging
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("Initializing QR Scanner Hardware Simulator Server...")

    engine = SimulatorEngine(settings)

    @asynccontextmanager
    async def lifespan(app):
        # Startup
        await engine.start()
        yield
        # Shutdown
        await engine.stop()

    app = create_app(engine)
    app.router.lifespan_context = lifespan

    logger.info("Starting Web API & UI server on http://%s:%d", settings.HOST, settings.PORT)
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level=settings.LOG_LEVEL.lower())


if __name__ == "__main__":
    main()
