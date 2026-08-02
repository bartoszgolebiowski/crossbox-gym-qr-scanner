import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from src.config import Settings

logger = logging.getLogger(__name__)

try:
    from awscrt import io, mqtt
    from awsiot import mqtt_connection_builder
    AWS_SDK_AVAILABLE = True
except ImportError:
    AWS_SDK_AVAILABLE = False
    logger.warning("awsiotsdk / awscrt is not available in environment. Real AWS IoT connections will fallback to mock.")


class AWSIoTPublisher:
    """Manages mTLS connection to AWS IoT Core and handles QR scan event publication."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.mock_mode = settings.MOCK_AWS or not AWS_SDK_AVAILABLE
        self._mqtt_connection: Optional[Any] = None
        self._is_connected = False
        self.published_messages_history = []  # useful for mock testing and verification

    def build_payload(self, raw_data: str) -> Dict[str, Any]:
        """Formats the payload according to PRD schema."""
        return {
            "event_id": str(uuid.uuid4()),
            "client_id": self.settings.AWS_IOT_CLIENT_ID,
            "timestamp": int(time.time()),
            "payload": {
                "raw_data": raw_data,
                "encoding": "utf-8"
            }
        }

    async def connect(self) -> bool:
        """Establishes mTLS MQTT connection to AWS IoT Core."""
        if self.mock_mode:
            logger.info("[MOCK AWS] Skipping real mTLS connection (MOCK_AWS=%s).", self.mock_mode)
            self._is_connected = True
            return True

        if not AWS_SDK_AVAILABLE:
            logger.error("awsiotsdk is not installed. Cannot establish real AWS connection.")
            return False

        # Validate certificate paths
        cert_p = self.settings.cert_path
        key_p = self.settings.key_path
        ca_p = self.settings.root_ca_path

        if not (cert_p.exists() and key_p.exists() and ca_p.exists()):
            logger.error(
                "Certificate files missing! Checked: cert='%s', key='%s', ca='%s'. Falling back to mock connection.",
                cert_p, key_p, ca_p
            )
            self.mock_mode = True
            self._is_connected = True
            return True

        try:
            logger.info("Initializing AWS IoT connection to '%s' (client_id='%s')...", self.settings.AWS_IOT_ENDPOINT, self.settings.AWS_IOT_CLIENT_ID)
            event_loop_group = io.EventLoopGroup(1)
            host_resolver = io.DefaultHostResolver(event_loop_group)
            client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

            self._mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=self.settings.AWS_IOT_ENDPOINT,
                cert_filepath=str(cert_p),
                pri_key_filepath=str(key_p),
                ca_filepath=str(ca_p),
                client_bootstrap=client_bootstrap,
                client_id=self.settings.AWS_IOT_CLIENT_ID,
                clean_session=False,
                keep_alive_secs=30
            )

            connect_future = self._mqtt_connection.connect()
            connect_future.result(timeout=10.0)
            self._is_connected = True
            logger.info("Successfully connected to AWS IoT Core.")
            return True

        except Exception as exc:
            logger.error("Failed to connect to AWS IoT Core: %s", exc)
            self._is_connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnects from AWS IoT Core."""
        logger.info("Disconnecting AWS IoT Publisher...")
        if self._mqtt_connection and self._is_connected and not self.mock_mode:
            try:
                disconnect_future = self._mqtt_connection.disconnect()
                disconnect_future.result(timeout=5.0)
            except Exception as exc:
                logger.warning("Error during AWS IoT disconnect: %s", exc)
        self._is_connected = False
        logger.info("AWS IoT Publisher disconnected.")

    async def publish_scan(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """Builds payload and publishes scan event to configured MQTT topic."""
        payload_dict = self.build_payload(raw_data)
        json_payload = json.dumps(payload_dict)

        if self.mock_mode:
            logger.info(
                "[MOCK AWS PUBLISH] Topic: '%s' | Payload: %s",
                self.settings.AWS_IOT_TOPIC, json_payload
            )
            self.published_messages_history.append(payload_dict)
            return payload_dict

        if not self._is_connected or not self._mqtt_connection:
            logger.error("Cannot publish: Not connected to AWS IoT Core. Attempting reconnect...")
            connected = await self.connect()
            if not connected:
                return None

        try:
            logger.info("Publishing QR scan to topic '%s'...", self.settings.AWS_IOT_TOPIC)
            publish_future, _ = self._mqtt_connection.publish(
                topic=self.settings.AWS_IOT_TOPIC,
                payload=json_payload,
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            publish_future.result(timeout=5.0)
            logger.info("Successfully published event ID '%s' to AWS IoT.", payload_dict["event_id"])
            self.published_messages_history.append(payload_dict)
            return payload_dict
        except Exception as exc:
            logger.error("Failed to publish message to AWS IoT: %s", exc)
            self._is_connected = False
            return None
