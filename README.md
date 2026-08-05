# AWS IoT Edge QR Scanner Engine

Kontenerowalna usługa w języku Python przeznaczona na urządzenia brzegowe (Raspberry Pi), służąca do bezobsługowego odczytu danych z fizycznych skanerów kodów QR (USB Virtual COM / Serial Port) oraz ich szyfrowanej mTLS i asynchronicznej publikacji do chmury **AWS IoT Core**.

---

## 🌟 Główne Cechy (Key Features)

- **Zero-Hardcode Configuration**: Pełna konfiguracja (porty, prędkości transmisji, certyfikaty, endpointy AWS IoT) wstrzykiwana przez plik `.env` / zmienne środowiskowe z walidacją `pydantic-settings`.
- **Dynamic Certificate Volume Mounting**: Certyfikaty mTLS nie są wbudowywane w obraz Docker. Są wstrzykiwane dynamicznie podczas uruchamiania kontenera przez wolumeny Docker w trybie Read-Only (`:ro`).
- **Standalone Cert Fetcher Script**: Skrypt Python `scripts/fetch_certs.py` pobierający certyfikaty z AWS Secrets Manager (`crossbox-gym/iot/certs`).
- **Manual Scan Trigger Script**: Skrypt Python `scripts/trigger_scan.py` do ręcznego wysyłania zdarzeń skanowania QR.
- **Hardware Simulator Service**: Dedykowany podprojekt w katalogu `./simulator` pozwalający na testy E2E bez fizycznego skanera.
- **Auto-Reconnect & Resilience**: Automatyczna obsługa rozłączenia kabla USB skanera oraz odzyskiwanie połączenia MQTT z brokerem AWS IoT Core.
- **Device Heartbeat**: Co 10 sekund publikowana jest wiadomość `heartbeat` na temat `gym/devices/{client_id}/heartbeat`, umożliwiająca backendowi wykrycie, gdy skaner jest offline.
- **Docker Ready**: Zoptymalizowany obraz Docker (`python:3.11-slim`) z `docker-compose.yml`.

---

## 📁 Struktura Projektu

```text
crossbox-gym-qr-scanner/
├── certs/                      # Katalog certyfikatów mTLS (wstrzykiwany przez wolumen :ro)
│   ├── AmazonRootCA1.pem
│   ├── device.pem.crt
│   └── private.pem.key
├── docs/                       # Dokumentacja PRD i planu wdrożeniowego
│   ├── prd.md
│   └── implementation_plan.md
├── scripts/                    # Skrypty pomocnicze
│   ├── fetch_certs.py         # Pobieranie certyfikatów z AWS Secrets Manager
│   └── trigger_scan.py        # Ręczne wyzwalanie skanów QR
├── simulator/                  # Dedykowany symulator sprzętowy + REST API UI (testy E2E)
│   ├── certs/
│   ├── src/
│   ├── static/
│   ├── tests/
│   ├── Dockerfile
│   └── docker-compose.yml
├── src/                        # Kod źródłowy aplikacji produkcyjnej
│   ├── __init__.py
│   ├── aws_publisher.py       # Publikator MQTT mTLS (awsiotsdk)
│   ├── config.py              # Moduł konfiguracji (pydantic-settings)
│   ├── main.py                # Główny orkiestrator usługi
│   └── serial_listener.py     # Czytnik portu szeregowego (pyserial)
├── tests/                      # Zestaw testów jednostkowych i integracyjnych
├── .env.example                # Wzorzec zmiennych środowiskowych
├── .env                        # Konfiguracja środowiskowa
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 🔑 Pobieranie Certyfikatów mTLS z AWS (`scripts/fetch_certs.py`)

Skrypt `scripts/fetch_certs.py` umożliwia pobranie certyfikatów z Secrets Manager (`crossbox-gym/iot/certs`).

```bash
# Pobranie certyfikatów z domyślnej nazwy sekretu (crossbox-gym/iot/certs):
python scripts/fetch_certs.py -s "crossbox-gym/iot/certs"
```

---

## ⚙️ Konfiguracja Środowiskowa (`.env`)

| Nazwa Zmiennej | Typ | Domyślna | Opis |
| --- | --- | --- | --- |
| `AWS_SECRET_NAME` | `String` | `crossbox-gym/iot/certs` | Nazwa sekretu w AWS Secrets Manager. |
| `AWS_REGION` | `String` | `eu-central-1` | Region AWS. |
| `SERIAL_PORT` | `String` | `/dev/ttyACM0` | Ścieżka do portu szeregowego skanera. |
| `SERIAL_BAUDRATE` | `Integer` | `9600` | Prędkość transmisji portu szeregowego. |
| `AWS_IOT_ENDPOINT` | `String` | **Wymagane** | Adres wywołania brokera AWS IoT (ATS Endpoint). |
| `AWS_IOT_CLIENT_ID` | `String` | `crossbox-qr-scanner-01` | Identyfikator klienta MQTT. |
| `AWS_IOT_TOPIC` | `String` | `gym/scanners/crossbox-qr-scanner-01/scan` | Temat MQTT publikacji zdarzeń. |
| `AWS_IOT_HEARTBEAT_INTERVAL_SECONDS` | `Integer` | `10` | Odstęp czasu (w sekundach) między kolejnymi wiadomościami heartbeat. |
| `AWS_IOT_HEARTBEAT_TOPIC` | `String` | `gym/devices/crossbox-qr-scanner-01/heartbeat` | Temat MQTT publikacji heartbeat urządzenia. |
| `AWS_CERT_DIR` | `String` | `/app/certs` | Ścieżka wewnątrz kontenera z certyfikatami. |
| `AWS_CERT_FILE` | `String` | `device.pem.crt` | Certyfikat urządzenia X.509. |
| `AWS_KEY_FILE` | `String` | `private.pem.key` | Klucz prywatny urządzenia. |
| `AWS_ROOT_CA_FILE` | `String` | `AmazonRootCA1.pem` | Certyfikat Root CA Amazon. |

---

## 🎯 Ręczne Wyzwalanie Skanów (`scripts/trigger_scan.py`)

Możesz wyzwalać konkretne skany kodów QR ręcznie ze skryptu:

```bash
python scripts/trigger_scan.py --qr "https://crossboxgym.pl/checkin/member/12345"
```

---

## � Heartbeat urządzenia

Silnik skanera publikuje cyklicznie wiadomość heartbeat na temat `gym/devices/{AWS_IOT_CLIENT_ID}/heartbeat` (domyślnie co 10 sekund).

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

## �🚀 Uruchomienie (Krok po Kroku)

### Wariant A: Symulator Sprzętu i REST API (Testy E2E w ./simulator)
```bash
cd simulator
docker compose up -d --build
```
Dostęp do interfejsu REST i Web UI pod adresem: `http://localhost:8000`

---

### Wariant B: Produkcyjne na Raspberry Pi (Docker Compose)
```bash
# 1. Pobierz certyfikaty z AWS Secrets Manager:
python scripts/fetch_certs.py -s "crossbox-gym/iot/certs"

# 2. Uruchom kontener za pomocą Docker Compose:
docker compose up -d --build
```
