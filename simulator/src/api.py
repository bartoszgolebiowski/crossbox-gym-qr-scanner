from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.simulator_engine import SimulatorEngine


class ScanTriggerRequest(BaseModel):
    qr_data: str = Field(..., description="QR code payload string to simulate scanning")


class AutoScanRequest(BaseModel):
    interval_seconds: float = Field(default=3.0, ge=0.5, le=60.0, description="Auto-scan interval in seconds")


def create_app(engine: SimulatorEngine) -> FastAPI:
    """FastAPI application factory for the QR Scanner Simulator."""
    app = FastAPI(
        title="AWS IoT QR Scanner Hardware Simulator API",
        description="REST API for triggering simulated QR scanner events and controlling AWS IoT publication.",
        version="1.0.0"
    )

    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_dashboard():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse({"message": "Simulator API is running."})

    @app.get("/api/v1/status", summary="Get simulator diagnostic status")
    async def get_status() -> Dict[str, Any]:
        return engine.get_status()

    @app.post("/api/v1/scan", summary="Trigger a simulated QR code scan event")
    async def trigger_scan(req: ScanTriggerRequest) -> Dict[str, Any]:
        if not req.qr_data or not req.qr_data.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="qr_data string cannot be empty."
            )
        event = await engine.trigger_scan(req.qr_data.strip())
        if not event:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to publish QR scan event to AWS IoT Core."
            )
        return {
            "status": "success",
            "message": "QR scan event published successfully",
            "event": event
        }

    @app.post("/api/v1/auto-scan/start", summary="Start automatic random QR code generator")
    async def start_auto_scan(req: AutoScanRequest) -> Dict[str, Any]:
        started = await engine.start_auto_scan(req.interval_seconds)
        if not started:
            return {"status": "warning", "message": "Auto-scan is already active"}
        return {
            "status": "success",
            "message": f"Auto-scan started with interval {req.interval_seconds}s"
        }

    @app.post("/api/v1/auto-scan/stop", summary="Stop automatic QR code generator")
    async def stop_auto_scan() -> Dict[str, Any]:
        stopped = await engine.stop_auto_scan()
        if not stopped:
            return {"status": "warning", "message": "Auto-scan was not active"}
        return {"status": "success", "message": "Auto-scan stopped"}

    @app.get("/api/v1/history", summary="Get history of published QR scan payloads")
    async def get_history() -> List[Dict[str, Any]]:
        return engine.publisher.published_history

    return app
