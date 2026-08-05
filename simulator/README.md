# AWS IoT Edge QR Scanner Hardware Simulator

Dedykowany kontenerowalny symulator sprzętowy urządzenia brzegowego (Raspberry Pi / USB QR Scanner) oraz publishingu do **AWS IoT Core**. 

Symulator bezfizycznie zastępuje podłączenie fizycznego czytnika kodów QR USB przez udostępnienie prostego interfejsu **REST API** oraz **panelu Web Dashboard UI**. Dzięki temu umożliwia szybkie testy **End-to-End (E2E)** całej architektury (AWS IoT Core -> AWS Rules -> Lambda -> Backend).

---

## 🌟 Główne Funkcje (Key Features)

- **AWS IoT Core mTLS Integration**: Wykorzystuje oficjalne SDK (`awsiotsdk`) i łączy się z brokera mTLS przy użyciu certyfikatów (`device.pem.crt`, `private.pem.key`, `AmazonRootCA1.pem`).
- **Zero-Hardcode Environment Config**: Parametry takie jak `AWS_SECRET_NAME` (`crossbox-gym/iot/certs`), `AWS_REGION`, `AWS_IOT_ENDPOINT`, `AWS_IOT_CLIENT_ID`, `AWS_IOT_TOPIC` (`gym/scanners/crossbox-qr-scanner-01/scan`), `AWS_CERT_DIR` konfiguruje się przez `.env`.
- **FastAPI REST API**: Dedykowane punkty końcowe HTTP (`POST /api/v1/scan`, `GET /api/v1/status`).
- **Manual Trigger Support**: Wysyłanie ręcznych zdarzeń skanowania z cURL lub ze skryptu `scripts/trigger_scan.py`.
- **Device Heartbeat**: Co 10 sekund publikowana jest wiadomość `heartbeat` na temat `gym/devices/{client_id}/heartbeat`, zgodnie z produkcyjnym kontraktem urządzenia brzegowego.
- **Glassmorphism Web Dashboard UI**: Wbudowana aplikacja webowa w przeglądarce pod adresem `http://localhost:8000`.
- **Docker Ready**: Zbudowane dla środowiska Docker / Docker Compose z podmontowaniem certyfikatów w trybie Read-Only (`:ro`).

---

## 📁 Struktura Symulatora (`./simulator`)

```text
simulator/
├── certs/                      # Katalog na certyfikaty mTLS (:ro mount w Dockerze)
│   ├── AmazonRootCA1.pem
│   ├── device.pem.crt
│   └── private.pem.key
├── src/                        # Kod źródłowy w Pythonie
│   ├── __init__.py
│   ├── api.py                 # FastAPI endpoints + montowanie static UI
│   ├── aws_publisher.py       # Klient MQTT mTLS (awsiotsdk)
│   ├── config.py              # Ustawienia z pydantic-settings
│   ├── main.py                # Punkt wejścia serwera (Uvicorn)
│   └── simulator_engine.py    # Orkiestrator skanera i wyzwalacza
├── static/                     # Web Dashboard UI (HTML / CSS / JS)
│   ├── app.js
│   ├── index.html
│   └── style.css
├── tests/                      # Testy API i silnika symulatora
│   ├── __init__.py
│   └── test_simulator_api.py
├── .dockerignore
├── .env.example
├── .env
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## ⚙️ Konfiguracja Środowiskowa (`.env`)

| Nazwa Zmiennej | Typ | Domyślna | Opis |
| --- | --- | --- | --- |
| `AWS_SECRET_NAME` | `String` | `crossbox-gym/iot/certs` | Nazwa sekretu w AWS Secrets Manager. |
| `AWS_REGION` | `String` | `eu-central-1` | Region AWS. |
| `AWS_IOT_ENDPOINT` | `String` | **Wymagane** | Adres brokera AWS IoT Core ATS Endpoint. |
| `AWS_IOT_CLIENT_ID` | `String` | `crossbox-qr-scanner-sim-01` | Identyfikator klienta MQTT. |
| `AWS_IOT_TOPIC` | `String` | `gym/scanners/crossbox-qr-scanner-01/scan` | Temat publikowania zdarzeń. |
| `AWS_IOT_HEARTBEAT_INTERVAL_SECONDS` | `Integer` | `10` | Odstęp czasu (w sekundach) między kolejnymi wiadomościami heartbeat. |
| `AWS_IOT_HEARTBEAT_TOPIC` | `String` | `gym/devices/crossbox-qr-scanner-01/heartbeat` | Temat publikowania heartbeat urządzenia. |
| `AWS_CERT_DIR` | `String` | `/app/certs` | Ścieżka wewnątrz kontenera z certyfikatami. |
| `AWS_CERT_FILE` | `String` | `device.pem.crt` | Certyfikat urządzenia. |
| `AWS_KEY_FILE` | `String` | `private.pem.key` | Klucz prywatny. |
| `AWS_ROOT_CA_FILE` | `String` | `AmazonRootCA1.pem` | Certyfikat Root CA Amazon. |
| `PORT` | `Integer` | `8000` | Port serwera HTTP / Web UI. |

---

## 🚀 Uruchomienie (Docker Compose)

### 1. Przygotuj certyfikaty
Umieść certyfikaty w katalogu `./simulator/certs/`:
- `device.pem.crt`
- `private.pem.key`
- `AmazonRootCA1.pem`

### 2. Skonfiguruj plik `.env`
Skopiuj `.env.example` do `.env` i ustaw swój `AWS_IOT_ENDPOINT` oraz temat MQTT (`gym/scanners/crossbox-qr-scanner-01/scan`).

### 3. Uruchom kontener
```bash
cd simulator
docker compose up -d --build
```

Aplikacja oraz Web UI będą dostępne pod adresem: **`http://localhost:8000`**

---

## � Heartbeat urządzenia

Symulator, podobnie jak produkcyjny silnik skanera, publikuje cyklicznie wiadomość heartbeat na temat `gym/devices/{AWS_IOT_CLIENT_ID}/heartbeat` (domyślnie co 10 sekund).

Przykładowy payload:

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

Backend może wykorzystać te wiadomości do raportowania statusu urządzenia (`ONLINE`/`OFFLINE`). Polityka AWS IoT musi zezwalać na publikację do tematu `gym/devices/*/heartbeat`:

```json
{
  "Effect": "Allow",
  "Action": ["iot:Publish"],
  "Resource": ["arn:aws:iot:{region}:{account}:topic/gym/devices/*/heartbeat"]
}
```

## �💻 Wywołania REST API & Manual Scripting

### Ręczne wyzwolenie ze skryptu Python:
```bash
python scripts/trigger_scan.py --qr "https://crossboxgym.pl/checkin/member/12345"
```

### Ręczne wyzwolenie z cURL:
```bash
curl -X POST "http://localhost:8000/api/v1/scan" \
     -H "Content-Type: application/json" \
     -d '{"qr_data": "https://crossboxgym.pl/checkin/member/12345"}'
```
