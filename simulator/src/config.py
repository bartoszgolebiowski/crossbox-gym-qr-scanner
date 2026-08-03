import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    """Configuration settings for the AWS IoT QR Scanner Simulator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    # AWS Secrets Manager & Region Parameters
    AWS_SECRET_NAME: Optional[str] = Field(
        default="crossbox-gym/iot/certs",
        description="Name of AWS Secret Manager containing mTLS certs"
    )
    AWS_REGION: str = Field(
        default="eu-central-1",
        description="AWS Region for Services"
    )

    # AWS IoT Core Settings
    AWS_IOT_ENDPOINT: str = Field(
        ...,
        description="AWS IoT Core Endpoint ATS URL"
    )
    AWS_IOT_CLIENT_ID: str = Field(
        default="crossbox-qr-scanner-01",
        description="MQTT Client ID for the simulator device"
    )
    AWS_IOT_TOPIC: str = Field(
        default="gym/scanners/crossbox-qr-scanner-01/scan",
        description="MQTT Topic for publishing QR scan events"
    )

    # mTLS Certificate File Locations
    AWS_CERT_DIR: str = Field(
        default="/app/certs",
        description="Directory path containing mTLS certs inside container/host"
    )
    AWS_CERT_FILE: str = Field(
        default="device.pem.crt",
        description="Device Certificate filename"
    )
    AWS_KEY_FILE: str = Field(
        default="private.pem.key",
        description="Private Key filename"
    )
    AWS_ROOT_CA_FILE: str = Field(
        default="AmazonRootCA1.pem",
        description="Amazon Root CA filename"
    )

    # Host & Web API Server Settings
    HOST: str = Field(default="0.0.0.0", description="API server host address")
    PORT: int = Field(default=8000, description="API server port")
    LOG_LEVEL: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARN, ERROR)")

    def _find_cert_file(self, primary_dir: str, primary_filename: str, fallback_filenames: list[str]) -> Path:
        primary_path = Path(primary_dir) / primary_filename
        if primary_path.exists():
            return primary_path

        project_root = Path(__file__).resolve().parent.parent
        search_dirs = [
            Path(primary_dir),
            project_root / "certs",
            project_root.parent / "certs",
            Path("certs"),
            Path("../certs"),
            Path("/app/certs"),
        ]

        filenames = [primary_filename] + [f for f in fallback_filenames if f != primary_filename]

        for d in search_dirs:
            for fn in filenames:
                candidate = d / fn
                if candidate.exists():
                    return candidate

        return primary_path

    @property
    def cert_path(self) -> Path:
        return self._find_cert_file(
            primary_dir=self.AWS_CERT_DIR,
            primary_filename=self.AWS_CERT_FILE,
            fallback_filenames=["certificate.pem.crt", "device.pem.crt", "cert.pem.crt"]
        )

    @property
    def key_path(self) -> Path:
        return self._find_cert_file(
            primary_dir=self.AWS_CERT_DIR,
            primary_filename=self.AWS_KEY_FILE,
            fallback_filenames=["private.pem.key", "private.key", "device.pem.key"]
        )

    @property
    def root_ca_path(self) -> Path:
        return self._find_cert_file(
            primary_dir=self.AWS_CERT_DIR,
            primary_filename=self.AWS_ROOT_CA_FILE,
            fallback_filenames=["AmazonRootCA1.pem", "root-ca.pem", "root.pem"]
        )



def get_simulator_settings() -> SimulatorSettings:
    """Factory function for loading simulator settings."""
    return SimulatorSettings()
