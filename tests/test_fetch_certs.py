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
