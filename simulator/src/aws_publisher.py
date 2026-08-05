import abc
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.config import SimulatorSettings

logger = logging.getLogger("SimulatorAWSPublisher")

try:
    from awscrt import io, mqtt
    from awsiot import mqtt_connection_builder
    AWS_SDK_AVAILABLE = True
except ImportError:
    AWS_SDK_AVAILABLE = False
    logger.warning("awsiotsdk / awscrt is not available in environment.")


class BaseIoTPublisher(abc.ABC):
    """Abstract Base Class / Interface for IoT MQTT Publishers."""

    @property
    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Returns current connection status."""
        pass

    @abc.abstractmethod
    async def connect(self) -> bool:
        """Establishes connection to AWS IoT Core broker."""
        pass

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Disconnects from AWS IoT Core broker."""
        pass

    @abc.abstractmethod
    async def publish_scan(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """Publishes a QR scan event payload."""
        pass

    @abc.abstractmethod
    async def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        qos: mqtt.QoS = mqtt.QoS.AT_LEAST_ONCE,
    ) -> Optional[Dict[str, Any]]:
        """Publish a JSON payload to any MQTT topic."""
        pass


class SimulatorAWSPublisher(BaseIoTPublisher):
    """Handles mTLS MQTT connection to AWS IoT Core for the simulated hardware device."""

    def __init__(self, settings: SimulatorSettings):
        self.settings = settings
        self._mqtt_connection: Optional[Any] = None
        self._is_connected = False
        self.published_history: List[Dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def build_payload(self, raw_data: str) -> Dict[str, Any]:
        """Formats QR scan payload matching the production edge scanner schema."""
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
        """Establishes mTLS MQTT connection to AWS IoT Core endpoint."""
        if not AWS_SDK_AVAILABLE:
            logger.error("awsiotsdk package is missing. Cannot establish real AWS connection.")
            self._is_connected = False
            return False

        cert_p = self.settings.cert_path
        key_p = self.settings.key_path
        ca_p = self.settings.root_ca_path

        if not (cert_p.exists() and key_p.exists() and ca_p.exists()):
            logger.error(
                "Certificates missing at: cert='%s', key='%s', ca='%s'. Cannot connect to AWS IoT Core.",
                cert_p, key_p, ca_p
            )
            self._is_connected = False
            return False

        try:
            logger.info(
                "Connecting to AWS IoT Core endpoint '%s' with client_id '%s'...",
                self.settings.AWS_IOT_ENDPOINT, self.settings.AWS_IOT_CLIENT_ID
            )
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
            logger.info("Successfully connected to AWS IoT Core via mTLS.")
            return True

        except Exception as exc:
            logger.error("Failed to establish AWS IoT Core mTLS connection: %s", exc)
            self._is_connected = False
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnects MQTT client from AWS IoT Core."""
        logger.info("Disconnecting AWS IoT Publisher...")
        if self._mqtt_connection and self._is_connected:
            try:
                disconnect_future = self._mqtt_connection.disconnect()
                disconnect_future.result(timeout=5.0)
            except Exception as exc:
                logger.warning("Error during AWS IoT disconnect: %s", exc)
        self._is_connected = False
        logger.info("AWS IoT Publisher disconnected.")

    async def publish_scan(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """Publishes QR code scan event to AWS IoT Core topic."""
        payload_dict = self.build_payload(raw_data)
        json_payload = json.dumps(payload_dict)

        if not self._is_connected or not self._mqtt_connection:
            logger.warning("Not connected to AWS IoT Core. Attempting reconnection...")
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
            logger.info("Successfully published event ID '%s' to AWS IoT Topic '%s'.", payload_dict["event_id"], self.settings.AWS_IOT_TOPIC)
            self.published_history.insert(0, payload_dict)
            if len(self.published_history) > 100:
                self.published_history.pop()
            return payload_dict
        except Exception as exc:
            logger.error("Failed to publish message to AWS IoT: %s", exc)
            self._is_connected = False
            return None

    async def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        qos: mqtt.QoS = mqtt.QoS.AT_LEAST_ONCE,
    ) -> Optional[Dict[str, Any]]:
        """Publishes a generic JSON payload to the specified MQTT topic."""
        if not self._is_connected or not self._mqtt_connection:
            logger.warning("Cannot publish to %s: not connected. Attempting reconnect...", topic)
            connected = await self.connect()
            if not connected:
                return None

        json_payload = json.dumps(payload)
        try:
            publish_future, _ = self._mqtt_connection.publish(
                topic=topic,
                payload=json_payload,
                qos=qos,
            )
            publish_future.result(timeout=5.0)
            logger.info("Published to topic '%s'.", topic)
            self.published_history.insert(0, payload)
            if len(self.published_history) > 100:
                self.published_history.pop()
            return payload
        except Exception as exc:
            logger.error("Failed to publish to %s: %s", topic, exc)
            self._is_connected = False
            return None


class StubIoTPublisher(BaseIoTPublisher):
    """Stub IoT Publisher implementation for unit and API testing without network calls."""

    def __init__(self, client_id: str = "test-client-id", topic: str = "gym/scanners/test/scan"):
        self.client_id = client_id
        self.topic = topic
        self._connected = True
        self.published_history: List[Dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def published_messages_history(self) -> List[Dict[str, Any]]:
        return self.published_history

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def publish_scan(self, raw_data: str) -> Optional[Dict[str, Any]]:
        if not self._connected:
            return None
        payload = {
            "event_id": str(uuid.uuid4()),
            "client_id": self.client_id,
            "timestamp": int(time.time()),
            "payload": {
                "raw_data": raw_data,
                "encoding": "utf-8"
            }
        }
        self.published_history.insert(0, payload)
        return payload

    async def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        qos: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """Records a generic published message in history."""
        if not self._connected:
            return None
        self.published_history.insert(0, {"topic": topic, **payload})
        if len(self.published_history) > 100:
            self.published_history.pop()
        return payload
