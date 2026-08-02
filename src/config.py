import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    # Serial Port Settings
    SERIAL_PORT: str = Field(default="/dev/ttyACM0", description="Path to serial device port")
    SERIAL_BAUDRATE: int = Field(default=9600, description="Serial port baudrate")

    # AWS IoT Core Settings
    AWS_IOT_ENDPOINT: str = Field(..., description="AWS IoT Core Endpoint ATS URL")
    AWS_IOT_CLIENT_ID: str = Field(default="rpi-qr-scanner-01", description="MQTT Client ID")
    AWS_IOT_TOPIC: str = Field(default="scanners/qr/data", description="MQTT Topic for publishing QR scans")

    # Certificate Settings
    AWS_CERT_DIR: str = Field(default="/app/certs", description="Directory path containing mTLS certs")
    AWS_CERT_FILE: str = Field(default="device.pem.crt", description="Certificate file name")
    AWS_KEY_FILE: str = Field(default="private.pem.key", description="Private key file name")
    AWS_ROOT_CA_FILE: str = Field(default="AmazonRootCA1.pem", description="Amazon Root CA file name")

    # System & Logging
    LOG_LEVEL: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARN, ERROR")

    # Mock & Testing flags
    MOCK_SERIAL: bool = Field(default=False, description="Enable simulated serial QR scanner")
    MOCK_SERIAL_INTERVAL: float = Field(default=3.0, description="Interval in seconds for mock QR code emission")
    MOCK_AWS: bool = Field(default=False, description="Enable mock AWS IoT publisher for offline testing")

    @property
    def cert_path(self) -> Path:
        return Path(self.AWS_CERT_DIR) / self.AWS_CERT_FILE

    @property
    def key_path(self) -> Path:
        return Path(self.AWS_CERT_DIR) / self.AWS_KEY_FILE

    @property
    def root_ca_path(self) -> Path:
        return Path(self.AWS_CERT_DIR) / self.AWS_ROOT_CA_FILE


def get_settings() -> Settings:
    """Factory function for retrieving settings instance."""
    return Settings()
