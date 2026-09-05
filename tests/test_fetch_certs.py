import json
from pathlib import Path
import pytest
from scripts.fetch_certs import save_certificates


def test_save_certificates_successful_creation(tmp_path: Path):
    """Verifies that save_certificates creates all cert files and config.json with correct content."""
    mock_secret_data = {
        "certificate_pem": "-----BEGIN CERTIFICATE-----\nMOCK_DEVICE_CERT\n-----END CERTIFICATE-----",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMOCK_PRIVATE_KEY\n-----END RSA PRIVATE KEY-----",
        "root_ca": "-----BEGIN CERTIFICATE-----\nMOCK_ROOT_CA\n-----END CERTIFICATE-----",
        "endpoint_address": "test-endpoint.iot.eu-central-1.amazonaws.com",
        "certificate_arn": "arn:aws:iot:eu-central-1:123456789012:cert/abc123",
        "certificate_id": "abc123"
    }

    save_certificates(
        secret_data=mock_secret_data,
        output_dir=tmp_path,
        cert_name="certificate.pem.crt",
        key_name="private.pem.key",
        ca_name="amazon-root-ca1.pem"
    )

    cert_file = tmp_path / "certificate.pem.crt"
    key_file = tmp_path / "private.pem.key"
    ca_file = tmp_path / "amazon-root-ca1.pem"
    config_file = tmp_path / "config.json"

    assert cert_file.exists()
    assert key_file.exists()
    assert ca_file.exists()
    assert config_file.exists()

    assert "MOCK_DEVICE_CERT" in cert_file.read_text(encoding="utf-8")
    assert "MOCK_PRIVATE_KEY" in key_file.read_text(encoding="utf-8")
    assert "MOCK_ROOT_CA" in ca_file.read_text(encoding="utf-8")

    config_data = json.loads(config_file.read_text(encoding="utf-8"))
    assert config_data["endpoint"] == "test-endpoint.iot.eu-central-1.amazonaws.com"
    assert config_data["certificate_arn"] == "arn:aws:iot:eu-central-1:123456789012:cert/abc123"
    assert config_data["certificate_id"] == "abc123"


def test_save_certificates_nested_multi_device(tmp_path: Path):
    """Verifies that save_certificates extracts proper device from multi-device secret."""
    mock_multi_secret = {
        "crossbox-qr-scanner-01": {
            "certificate_pem": "-----BEGIN CERTIFICATE-----\nSCANNER_CERT\n-----END CERTIFICATE-----",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nSCANNER_KEY\n-----END RSA PRIVATE KEY-----",
            "root_ca": "-----BEGIN CERTIFICATE-----\nROOT_CA\n-----END CERTIFICATE-----",
            "endpoint_address": "scanner-endpoint.iot.eu-central-1.amazonaws.com",
            "certificate_arn": "arn:aws:iot:eu-central-1:123456789012:cert/scanner-123",
            "certificate_id": "scanner-123"
        },
        "crossbox-locker-relay-01": {
            "certificate_pem": "-----BEGIN CERTIFICATE-----\nLOCKER_CERT\n-----END CERTIFICATE-----",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nLOCKER_KEY\n-----END RSA PRIVATE KEY-----",
            "root_ca": "-----BEGIN CERTIFICATE-----\nROOT_CA\n-----END CERTIFICATE-----",
            "endpoint_address": "locker-endpoint.iot.eu-central-1.amazonaws.com",
            "certificate_arn": "arn:aws:iot:eu-central-1:123456789012:cert/locker-456",
            "certificate_id": "locker-456"
        }
    }

    meta = save_certificates(
        secret_data=mock_multi_secret,
        output_dir=tmp_path,
        thing_name="crossbox-qr-scanner-01"
    )

    assert meta["endpoint"] == "scanner-endpoint.iot.eu-central-1.amazonaws.com"
    assert meta["certificate_id"] == "scanner-123"
    assert (tmp_path / "device.pem.crt").exists()
    assert (tmp_path / "certificate.pem.crt").exists()
    assert (tmp_path / "private.pem.key").exists()
    assert "SCANNER_CERT" in (tmp_path / "device.pem.crt").read_text(encoding="utf-8")
    assert "SCANNER_KEY" in (tmp_path / "private.pem.key").read_text(encoding="utf-8")


def test_update_env_file(tmp_path: Path):
    """Verifies that update_env_file creates or updates .env with proper AWS IoT values."""
    from scripts.fetch_certs import update_env_file

    env_path = tmp_path / ".env"
    env_path.write_text("AWS_IOT_ENDPOINT=old-endpoint\nLOG_LEVEL=DEBUG\nSERIAL_PORT=/dev/ttyACM0\n", encoding="utf-8")

    update_env_file(
        env_file=env_path,
        endpoint="a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com",
        thing_name="crossbox-qr-scanner-01",
        region="eu-central-1",
        serial_port="/dev/ttyUSB0"
    )

    content = env_path.read_text(encoding="utf-8")
    assert "AWS_IOT_ENDPOINT=a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com" in content
    assert "AWS_IOT_CLIENT_ID=crossbox-qr-scanner-01" in content
    assert "AWS_IOT_TOPIC=gym/scanners/crossbox-qr-scanner-01/scan" in content
    assert "AWS_IOT_HEARTBEAT_TOPIC=gym/devices/crossbox-qr-scanner-01/heartbeat" in content
    assert "SERIAL_PORT=/dev/ttyUSB0" in content
    assert "LOG_LEVEL=DEBUG" in content  # Preserved

