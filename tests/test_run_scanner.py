import json
from pathlib import Path
import pytest
from run_scanner import extract_device_credentials, save_certificates, update_env_configuration


def test_extract_device_credentials_multi_dict():
    secret_data = {
        "crossbox-qr-scanner-01": {
            "certificate_pem": "SCANNER_CERT",
            "private_key": "SCANNER_KEY"
        },
        "crossbox-locker-relay-01": {
            "certificate_pem": "LOCKER_CERT",
            "private_key": "LOCKER_KEY"
        }
    }
    extracted = extract_device_credentials(secret_data, "crossbox-qr-scanner-01")
    assert extracted["certificate_pem"] == "SCANNER_CERT"
    assert extracted["private_key"] == "SCANNER_KEY"


def test_extract_device_credentials_flat():
    secret_data = {
        "certificate_pem": "DIRECT_CERT",
        "private_key": "DIRECT_KEY"
    }
    extracted = extract_device_credentials(secret_data, "crossbox-qr-scanner-01")
    assert extracted["certificate_pem"] == "DIRECT_CERT"


def test_save_certificates_run_scanner(tmp_path: Path):
    device_data = {
        "certificate_pem": "-----BEGIN CERTIFICATE-----\nSAMPLE\n-----END CERTIFICATE-----",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nKEY\n-----END RSA PRIVATE KEY-----",
        "root_ca": "-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----",
        "certificate_arn": "arn:aws:iot:test:cert/123",
        "certificate_id": "123"
    }
    save_certificates(
        device_data=device_data,
        output_dir=tmp_path,
        endpoint="test.iot.eu-central-1.amazonaws.com",
        thing_name="crossbox-qr-scanner-01"
    )

    assert (tmp_path / "device.pem.crt").exists()
    assert (tmp_path / "certificate.pem.crt").exists()
    assert (tmp_path / "private.pem.key").exists()
    assert (tmp_path / "AmazonRootCA1.pem").exists()
    assert (tmp_path / "config.json").exists()

    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["endpoint"] == "test.iot.eu-central-1.amazonaws.com"
    assert config["thing_name"] == "crossbox-qr-scanner-01"


def test_update_env_configuration(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("CUSTOM_VAR=hello\nLOG_LEVEL=DEBUG\n", encoding="utf-8")

    update_env_configuration(
        env_file_path=env_file,
        endpoint="a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com",
        thing_name="crossbox-qr-scanner-01",
        region="eu-central-1",
        serial_port="/dev/ttyACM0",
        mock_serial=True
    )

    content = env_file.read_text(encoding="utf-8")
    assert "AWS_IOT_ENDPOINT=a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com" in content
    assert "AWS_IOT_CLIENT_ID=crossbox-qr-scanner-01" in content
    assert "SERIAL_PORT=/dev/ttyACM0" in content
    assert "MOCK_SERIAL=true" in content
    assert "CUSTOM_VAR=hello" in content
    assert "LOG_LEVEL=DEBUG" in content
