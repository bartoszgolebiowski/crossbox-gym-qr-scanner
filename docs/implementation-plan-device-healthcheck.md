# Implementation Plan: Device Heartbeat for Healthcheck

> **Repository:** `crossbox-gym-qr-scanner` (Raspberry Pi / USB QR scanner engine)  
> **Scope:** Add periodic heartbeat publishing so the backend can detect when the scanner is offline.

---

## 1. Goal & Decisions

- **The backend will report the scanner as OFFLINE if no heartbeat arrives within 30 seconds.**
- **Heartbeat topic:** `gym/devices/{thingName}/heartbeat`
- **Heartbeat interval:** 10 seconds (must be well under the 30 s backend threshold).
- **Thing Name:** `crossbox-qr-scanner-01` (matches `lib/config/iot-fleet.json` in the backend repo).
- **Transport:** MQTT over mTLS to AWS IoT Core, using the existing `awsiotsdk` publisher.
- **Scope:** add a periodic heartbeat task to the existing `QRScannerEngine`.

---

## 2. Architecture

```mermaid
flowchart LR
    Scanner[QRScannerEngine] --"MQTT publish"--> HB[gym/devices/{thingName}/heartbeat]
    HB --> IoT[AWS IoT Core]
    IoT --"Topic Rule"--> Lambda[DeviceHeartbeatHandler]
    Lambda --"write last_seen"--> DB[(DynamoDB DevicePresence)]
```

---

## 3. Files to Change / Create

| # | File | Change |
|---|---|---|
| 1 | `src/aws_publisher.py` | Add a generic `publish(topic, payload, qos=1)` method to `BaseIoTPublisher`, `AWSIoTPublisher`, and `StubIoTPublisher`. |
| 2 | `src/config.py` | Add `AWS_IOT_HEARTBEAT_INTERVAL_SECONDS` (default `10`) and `AWS_IOT_HEARTBEAT_TOPIC`. |
| 3 | `src/main.py` | Add a heartbeat task to `QRScannerEngine` that publishes while running. |
| 4 | `.env.example` | Add new environment variables. |
| 5 | `tests/test_aws_publisher.py` | Add publish tests. |
| 6 | `tests/test_main.py` (or `test_engine.py`) | Add heartbeat timing/publishing tests. |
| 7 | `README.md` | Document heartbeat behavior and required IoT policy permission. |

---

## 4. Heartbeat Payload Contract

Publish JSON matching the backend contract:

```json
{
  "thingName": "crossbox-qr-scanner-01",
  "deviceType": "HDWR-HD360-QR-Scanner",
  "status": "online",
  "timestamp": "2026-08-05T12:34:56.789Z",
  "uptime_ms": 3600000,
  "version": "1.0.0"
}
```

**Required fields:**
- `thingName` — must match the configured Thing Name.
- `deviceType` — `"HDWR-HD360-QR-Scanner"`.
- `status` — `"online"` while the service is running.
- `timestamp` — ISO 8601 UTC.

**Optional fields:**
- `uptime_ms` — device uptime.
- `version` — firmware version.

---

## 5. Phase-by-Phase Implementation

### Phase 1 — Add generic publish capability

In `src/aws_publisher.py`:

1. Extend `BaseIoTPublisher`:

```python
@abc.abstractmethod
async def publish(self, topic: str, payload: Dict[str, Any], qos: mqtt.QoS = mqtt.QoS.AT_LEAST_ONCE) -> Optional[Dict[str, Any]]:
    """Publish a JSON payload to any MQTT topic."""
```

2. Implement in `AWSIoTPublisher`:

```python
async def publish(self, topic: str, payload: Dict[str, Any], qos: mqtt.QoS = mqtt.QoS.AT_LEAST_ONCE) -> Optional[Dict[str, Any]]:
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
        self.published_messages_history.append(payload)
        return payload
    except Exception as exc:
        logger.error("Failed to publish to %s: %s", topic, exc)
        self._is_connected = False
        return None
```

3. Implement in `StubIoTPublisher`:

```python
async def publish(self, topic: str, payload: Dict[str, Any], qos: Any = None) -> Optional[Dict[str, Any]]:
    if not self._connected:
        return None
    self.published_messages_history.append({"topic": topic, **payload})
    return payload
```

### Phase 2 — Configuration

In `src/config.py`:

```python
from pydantic import Field

AWS_IOT_HEARTBEAT_INTERVAL_SECONDS: int = Field(default=10, ge=1, le=300)
AWS_IOT_HEARTBEAT_TOPIC: str = Field(default="gym/devices/crossbox-qr-scanner-01/heartbeat")
```

Add to `.env.example`:

```env
AWS_IOT_HEARTBEAT_INTERVAL_SECONDS=10
AWS_IOT_HEARTBEAT_TOPIC=gym/devices/crossbox-qr-scanner-01/heartbeat
```

### Phase 3 — Heartbeat task in QRScannerEngine

In `src/main.py`:

1. Import `datetime` and `time` if needed.
2. Update `QRScannerEngine.__init__`:

```python
import time

class QRScannerEngine:
    def __init__(...):
        ...
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._start_time = time.monotonic()
```

3. Start the heartbeat after connection:

```python
async def start(self) -> None:
    logger.info("Starting QRScannerEngine...")
    self._running = True
    await self.publisher.connect()
    self._worker_task = asyncio.create_task(self._queue_worker())
    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    await self.listener.start()
    logger.info("QRScannerEngine is fully operational.")
```

4. Stop the heartbeat on shutdown:

```python
async def stop(self) -> None:
    logger.info("Stopping QRScannerEngine...")
    self._running = False
    await self.listener.stop()

    for task in (self._worker_task, self._heartbeat_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    await self.publisher.disconnect()
    logger.info("QRScannerEngine stopped.")
```

5. Add the heartbeat loop and builder:

```python
import datetime

async def _heartbeat_loop(self) -> None:
    while self._running:
        try:
            await self._send_heartbeat()
            await asyncio.sleep(self.settings.AWS_IOT_HEARTBEAT_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Heartbeat error: %s", exc)
            await asyncio.sleep(1)

async def _send_heartbeat(self) -> None:
    payload = {
        "thingName": self.settings.AWS_IOT_CLIENT_ID,
        "deviceType": "HDWR-HD360-QR-Scanner",
        "status": "online",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "uptime_ms": int((time.monotonic() - self._start_time) * 1000),
        "version": "1.0.0",
    }
    await self.publisher.publish(self.settings.AWS_IOT_HEARTBEAT_TOPIC, payload)
```

### Phase 4 — Update AWS IoT Policy

The backend IoT policy must allow the scanner to publish to the heartbeat topic. After the backend plan is applied, the policy will include:

```json
{
  "Effect": "Allow",
  "Action": ["iot:Publish"],
  "Resource": ["arn:aws:iot:{region}:{account}:topic/gym/devices/*/heartbeat"]
}
```

If you rotate certificates or redeploy the backend, refetch certificates from AWS Secrets Manager (`crossbox-gym/iot/certs`) so the updated policy is attached.

### Phase 5 — Tests

1. `tests/test_aws_publisher.py`:

```python
async def test_stub_publisher_records_generic_publish():
    pub = StubIoTPublisher()
    result = await pub.publish("gym/devices/test/heartbeat", {"status": "online"})
    assert result is not None
    assert pub.published_messages_history[-1]["status"] == "online"
```

2. Add `tests/test_main.py` or extend `test_integration.py`:

```python
async def test_engine_publishes_heartbeat():
    settings = Settings(
        AWS_IOT_ENDPOINT="test-ats.iot.eu-central-1.amazonaws.com",
        AWS_IOT_HEARTBEAT_INTERVAL_SECONDS=0.05,
        MOCK_SERIAL=True,
    )
    pub = StubIoTPublisher()
    engine = QRScannerEngine(settings=settings, publisher=pub)
    await engine.start()
    await asyncio.sleep(0.15)
    await engine.stop()
    assert any(
        msg.get("topic") == settings.AWS_IOT_HEARTBEAT_TOPIC
        for msg in pub.published_messages_history
    )
```

---

## 6. Verification

1. Run tests: `pytest tests/ -v`
2. Start the scanner locally or in Docker:

```bash
python scripts/fetch_certs.py -s "crossbox-gym/iot/certs"
docker compose up -d --build
```

3. In the AWS IoT Core console → Test → MQTT test client, subscribe to `gym/devices/crossbox-qr-scanner-01/heartbeat`.
4. Confirm a message arrives every 10 seconds.
5. In the backend repo, deploy the healthcheck changes.
6. Stop the scanner container and wait 30+ seconds.
7. Call the backend health endpoint:

```bash
curl "https://{api}/admin/locations/{locationId}/devices/crossbox-qr-scanner-01/health"
```

Expected: `{"status":"OFFLINE","connected":false}`.

8. Restart the scanner, wait 10 s, call the endpoint again.

Expected: `{"status":"ONLINE","connected":true}`.

---

## 7. Notes

- The heartbeat task runs independently from the scan queue worker. It must not block QR scan processing.
- Keep the heartbeat payload small (<1 KB) to minimize bandwidth.
- Do not publish heartbeats before the MQTT connection is established.
- If you add device metrics later (e.g. scan count, temperature), extend the heartbeat payload; the backend will store them opaquely.
