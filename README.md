# AWS IoT Edge QR Scanner Engine

Kontenerowalna usługa w języku Python przeznaczona na urządzenia brzegowe (Raspberry Pi), służąca do bezobsługowego odczytu danych z fizycznych skanerów kodów QR (USB Virtual COM / Serial Port) oraz ich szyfrowanej mTLS i asynchronicznej publikacji do chmury **AWS IoT Core**.

---

## 🌟 Główne Cechy (Key Features)

- **Zero-Hardcode Configuration**: Pełna konfiguracja (porty, prędkości transmisji, certyfikaty, endpointy AWS IoT) wstrzykiwana przez plik `.env` / zmienne środowiskowe z walidacją `pydantic-settings`.
- **Dynamic Certificate Volume Mounting**: Certyfikaty mTLS nie są wbudowywane w obraz Docker. Są wstrzykiwane dynamicznie podczas uruchamiania kontenera przez wolumeny Docker w trybie Read-Only (`:ro`).
- **Standalone Cert Fetcher Script**: Przygotowany skrypt Python `scripts/fetch_certs.py` pobierający certyfikaty z AWS Secrets Manager do zdefiniowanych ścieżek.
- **Auto-Reconnect & Resilience**: Automatyczna obsługa rozłączenia kabla USB skanera oraz odzyskiwanie połączenia MQTT z brokerem AWS IoT Core.
- **Hardware & AWS Simulator**: Wbudowany tryb symulacji (`MOCK_SERIAL=true`, `MOCK_AWS=true`) pozwalający na łatwy rozwój i testowanie bez fizycznego skanera USB oraz bez aktywnego konta AWS.
- **Docker Ready**: Przygotowany zoptymalizowany obraz Docker (`python:3.11-slim`) z `docker-compose.yml`.
- **Comprehensive Testing Suite**: Zestaw testów jednostkowych i integracyjnych z symulatorem sprzętu.

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
│   └── fetch_certs.py         # Skrypt CLI do pobierania certyfikatów z AWS Secrets Manager
├── src/                        # Kod źródłowy aplikacji
│   ├── __init__.py
│   ├── aws_publisher.py       # Publikator MQTT mTLS (awsiotsdk)
│   ├── config.py              # Moduł konfiguracji (pydantic-settings)
│   ├── main.py                # Główny orkiestrator usługi
│   └── serial_listener.py     # Czytnik portu szeregowego (pyserial)
├── tests/                      # Zestaw testów jednostkowych i integracyjnych
│   ├── __init__.py
│   ├── test_aws_publisher.py
│   ├── test_config.py
│   ├── test_fetch_certs.py
│   ├── test_integration.py   # Testy end-to-end z symulatorem
│   └── test_serial_listener.py
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

Skrypt `scripts/fetch_certs.py` umożliwia pobranie certyfikatów przed uruchomieniem kontenera Docker.

### Wymagania i Domyślne Parametry:
- `--secret-name` (`-s`): **Wymagana** nazwa sekretu w AWS Secrets Manager (np. `rpi-qr-scanner/certs` lub ze zmiennej `AWS_SECRET_NAME`).
- `--region` (`-r`): Domyślnie **`eu-central-1`** (lub ze zmiennej `AWS_REGION`).
- Ścieżki docelowe: Domyślnie **`./certs/`**, **`device.pem.crt`**, **`private.pem.key`**, **`AmazonRootCA1.pem`**.

### Przykład wywołania CLI:

```bash
# 1. Pobranie certyfikatów (wymagana nazwa sekretu):
python scripts/fetch_certs.py --secret-name "rpi-qr-scanner/certs"

# Albo wskazując własne parametry:
python scripts/fetch_certs.py -s "my-qr-scanner-certs" -r "eu-central-1" -o "./certs"
```

---

## ⚙️ Konfiguracja Środowiskowa (`.env`)

| Nazwa Zmiennej | Typ | Domyślna | Opis |
| --- | --- | --- | --- |
| `AWS_SECRET_NAME` | `String` | **Wymagane** | Nazwa sekretu w AWS Secrets Manager. |
| `AWS_REGION` | `String` | `eu-central-1` | Region AWS. |
| `SERIAL_PORT` | `String` | `/dev/ttyACM0` | Ścieżka do portu szeregowego skanera. |
| `SERIAL_BAUDRATE` | `Integer` | `9600` | Prędkość transmisji portu szeregowego. |
| `AWS_IOT_ENDPOINT` | `String` | **Wymagane** | Adres wywołania brokera AWS IoT (ATS Endpoint). |
| `AWS_IOT_CLIENT_ID` | `String` | `rpi-qr-scanner-01` | Identyfikator klienta MQTT. |
| `AWS_IOT_TOPIC` | `String` | `scanners/qr/data` | Temat MQTT publikacji zdarzeń. |
| `AWS_CERT_DIR` | `String` | `/app/certs` | Ścieżka wewnątrz kontenera z certyfikatami. |
| `AWS_CERT_FILE` | `String` | `device.pem.crt` | Certyfikat urządzenia X.509. |
| `AWS_KEY_FILE` | `String` | `private.pem.key` | Klucz prywatny urządzenia. |
| `AWS_ROOT_CA_FILE` | `String` | `AmazonRootCA1.pem` | Certyfikat Root CA Amazon. |

---

## 🚀 Instrukcja Uruchomienia (Krok po Kroku)

### Wariant A: Szybki Test Lokalny (Z Symulatorem - Bez Skanera USB i Bez AWS)

```bash
# 1. Zainstaluj pakiety
pip install -r requirements.txt

# 2. W .env upewnij się, że włączone są tryby mock:
# MOCK_SERIAL=true
# MOCK_AWS=true

# 3. Uruchom aplikację:
python -m src.main
```

---

### Wariant B: Uruchomienie Zestawu Testów (Unit & Integration Tests)

```bash
pytest -v
```

---

### Wariant C: Uruchomienie Produkcyjne na Raspberry Pi (Docker Compose)

```bash
# 1. Pobierz certyfikaty z AWS Secrets Manager (wymaga nazwy sekretu):
python scripts/fetch_certs.py -s "rpi-qr-scanner/certs"

# 2. Uruchom kontener za pomocą Docker Compose:
docker compose up -d --build

# 3. Podgląd logów i zatrzymanie:
docker compose logs -f
docker compose down
```
