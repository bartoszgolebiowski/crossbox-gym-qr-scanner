import os
from pathlib import Path
import pytest
from src.config import Settings, get_settings


def test_default_settings(monkeypatch):
    """Verifies default fallback values for Settings."""
    for field_name in Settings.model_fields.keys():
        monkeypatch.delenv(field_name, raising=False)

    monkeypatch.setenv("AWS_IOT_ENDPOINT", "test-ats.iot.eu-central-1.amazonaws.com")

    settings = Settings(_env_file=None)
    assert settings.SERIAL_PORT == "/dev/ttyACM0"
    assert settings.SERIAL_BAUDRATE == 9600
    assert settings.AWS_IOT_ENDPOINT == "test-ats.iot.eu-central-1.amazonaws.com"
    assert settings.AWS_IOT_CLIENT_ID == "crossbox-qr-scanner-01"
    assert settings.AWS_IOT_TOPIC == "gym/scanners/crossbox-qr-scanner-01/scan"
    assert settings.LOG_LEVEL == "INFO"


def test_custom_environment_overrides(monkeypatch):
    """Verifies that custom env vars override defaults."""
    monkeypatch.setenv("SERIAL_PORT", "/dev/ttyUSB0")
    monkeypatch.setenv("SERIAL_BAUDRATE", "115200")
    monkeypatch.setenv("AWS_IOT_ENDPOINT", "custom-endpoint.iot.aws.com")
    monkeypatch.setenv("AWS_IOT_CLIENT_ID", "custom-scanner-id")
    monkeypatch.setenv("AWS_IOT_TOPIC", "gym/scanners/custom-scanner-id/scan")
    monkeypatch.setenv("AWS_CERT_DIR", "/custom/certs")
    monkeypatch.setenv("MOCK_SERIAL", "true")

    settings = Settings()
    assert settings.SERIAL_PORT == "/dev/ttyUSB0"
    assert settings.SERIAL_BAUDRATE == 115200
    assert settings.AWS_IOT_ENDPOINT == "custom-endpoint.iot.aws.com"
    assert settings.AWS_IOT_CLIENT_ID == "custom-scanner-id"
    assert settings.AWS_IOT_TOPIC == "gym/scanners/custom-scanner-id/scan"
    assert settings.cert_path == Path("/custom/certs/device.pem.crt")
    assert settings.key_path == Path("/custom/certs/private.pem.key")
    assert settings.root_ca_path == Path("/custom/certs/AmazonRootCA1.pem")
    assert settings.MOCK_SERIAL is True


def test_missing_required_endpoint(monkeypatch):
    """Verifies that missing required AWS_IOT_ENDPOINT raises ValidationError."""
    monkeypatch.delenv("AWS_IOT_ENDPOINT", raising=False)
    with pytest.raises(Exception):
        Settings(_env_file=None)
