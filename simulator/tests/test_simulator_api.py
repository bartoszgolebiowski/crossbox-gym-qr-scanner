import pytest
from httpx import AsyncClient, ASGITransport
from src.api import create_app
from src.config import SimulatorSettings
from src.simulator_engine import SimulatorEngine
from src.aws_publisher import StubIoTPublisher


@pytest.fixture
def test_engine():
    settings = SimulatorSettings(
        AWS_IOT_ENDPOINT="mock-ats.iot.eu-central-1.amazonaws.com",
        AWS_IOT_CLIENT_ID="sim-test-01",
        AWS_IOT_TOPIC="gym/scanners/crossbox-qr-scanner-01/scan",
        AWS_SECRET_NAME="crossbox-gym/iot/certs"
    )
    stub_pub = StubIoTPublisher(
        client_id=settings.AWS_IOT_CLIENT_ID,
        topic=settings.AWS_IOT_TOPIC
    )
    return SimulatorEngine(settings=settings, publisher=stub_pub)


@pytest.fixture
def app(test_engine):
    return create_app(test_engine)


@pytest.mark.asyncio
async def test_simulator_status_endpoint(app, test_engine):
    await test_engine.start()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["aws_iot_client_id"] == "sim-test-01"
        assert data["aws_secret_name"] == "crossbox-gym/iot/certs"
        assert data["aws_connected"] is True
    await test_engine.stop()


@pytest.mark.asyncio
async def test_trigger_scan_endpoint(app, test_engine):
    await test_engine.start()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        payload = {"qr_data": "https://crossboxgym.pl/checkin/member/9999"}
        response = await client.post("/api/v1/scan", json=payload)
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["status"] == "success"
        assert res_data["event"]["payload"]["raw_data"] == "https://crossboxgym.pl/checkin/member/9999"
        assert res_data["event"]["client_id"] == "sim-test-01"

        # Check history
        hist_response = await client.get("/api/v1/history")
        assert hist_response.status_code == 200
        history = hist_response.json()
        assert len(history) == 1
        assert history[0]["payload"]["raw_data"] == "https://crossboxgym.pl/checkin/member/9999"
    await test_engine.stop()


@pytest.mark.asyncio
async def test_auto_scan_endpoints(app, test_engine):
    await test_engine.start()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        start_res = await client.post("/api/v1/auto-scan/start", json={"interval_seconds": 1.0})
        assert start_res.status_code == 200
        assert test_engine.auto_scan_active is True

        stop_res = await client.post("/api/v1/auto-scan/stop")
        assert stop_res.status_code == 200
        assert test_engine.auto_scan_active is False
    await test_engine.stop()
