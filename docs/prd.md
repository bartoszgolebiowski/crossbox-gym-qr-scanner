Oto propozycja dokumentu PRD (Product Requirement Document) dla modularnej usłudze skanera QR na Raspberry Pi z integracją AWS IoT Core.

Struktura została zaprojektowana zgodnie z regułą **Zero-Hardcode** – cała konfiguracja urządzeń, portów, tematów MQTT i certyfikatów jest dynamiczna i wstrzykiwana przez środowisko lub wolumeny.

---

# PRD: AWS IoT Edge QR Scanner Engine

## 1. Przegląd i Cel Projektu (Overview)

Celem projektu jest stworzenie bezobsługowej, konteneryzowanej usługi (Docker) uruchamianej na urządzeniach brzegowych (Raspberry Pi), której zadaniem jest odczyt danych z dowolnych kodów QR przesyłanych przez skaner USB (praca w trybie Virtual COM / Serial Port) oraz ich asynchroniczne i bezpieczne publikowanie do chmury **AWS IoT Core**.

Urządzenie ma działać w modelu **Plug-and-Play**: parametryzacja odbywa się wyłącznie poprzez plik `.env` / zmienne środowiskowe oraz dynamicznie podpinane wolumeny.

---

## 2. Architektura Systemu

```
[Skaner HD360 (USB)] 
        │ /dev/tty*
        ▼
[Docker Container (Python)] 
   ├── Serial Monitor Service (pyserial)
   ├── Config Manager (pydantic-settings / env)
   └── AWS IoT Publisher (awsiotsdk / mTLS)
        │
        ▼ mTLS (Certyfikaty X.509)
[AWS IoT Core MQTT Broker]

```

---

## 3. Wymagania Funkcjonalne (Functional Requirements)

* **FR-01: Auto-wykrywanie i Nasłuch Portu Szeregowego**
* System musi otwierać i kontrolować połączenie z portem szeregowym wskazanym w zmiennej środowiskowej.
* System musi automatycznie rekonfigurować i ponawiać próbę połączenia (`auto-reconnect`) w przypadku fizycznego odłączenia skanera USB.


* **FR-02: Przetwarzanie Strumienia Danych z QR**
* System musi wspierać dowolną treść zawartą w kodach QR (URL, dowolny tekst, ciągi JSON, bajty).
* System musi czyścić surowy odczyt ze znaków końca linii (`\r`, `\n`) oraz wspierać kodowanie UTF-8.


* **FR-03: Komunikacja mTLS z AWS IoT Core**
* System musi ustanawiać szyfrowane połączenie MQTT po mTLS przy użyciu certyfikatu urządzenia (`.pem.crt`), klucza prywatnego (`.pem.key`) oraz Root CA.
* Scieżki do plików certyfikatów muszą być konfigurowalne przez zmienne środowiskowe.


* **FR-04: Publikacja Zdarzeń (Payload Schema)**
* Treść zdarzenia wysyłana na broker MQTT musi być sformatowanym obiektem JSON zawierającym meta-dane skanu.


* **FR-05: Konfiguracja typu "Zero-Hardcode"**
* Brak jakichkolwiek wartości statycznych (URL-e, nazwy portów, ID urządzeń, tematy MQTT) w kodzie źródłowym.



---

## 4. Konfiguracja Środowiskowa (Environment & Config Specs)

Wszystkie parametry sterujące działaniem kontenera przekazywane są za pomocą zmiennych środowiskowych.

### Tabela Zmiennych Środowiskowych

| Nazwa Zmiennej | Typ | Domyślna Wartość | Opis |
| --- | --- | --- | --- |
| `SERIAL_PORT` | `String` | `/dev/ttyACM0` | Ścieżka do urządzenia portu szeregowego w kontenerze. |
| `SERIAL_BAUDRATE` | `Integer` | `9600` | Prędkość transmisji portu szeregowego. |
| `AWS_IOT_ENDPOINT` | `String` | **Wymagane** | Adres wywołania brokera AWS IoT (np. `xxx-ats.iot.eu-central-1.amazonaws.com`). |
| `AWS_IOT_CLIENT_ID` | `String` | `rpi-qr-scanner-01` | Unikalny identyfikator klienta MQTT w AWS. |
| `AWS_IOT_TOPIC` | `String` | `scanners/qr/data` | Temat MQTT, na który publikowane są zdarzenia. |
| `AWS_CERT_DIR` | `String` | `/app/certs` | Ścieżka bazowa do katalogu z certyfikatami wewnątrz kontenera. |
| `AWS_CERT_FILE` | `String` | `device.pem.crt` | Nazwa pliku certyfikatu urządzenia. |
| `AWS_KEY_FILE` | `String` | `private.pem.key` | Nazwa pliku klucza prywatnego. |
| `AWS_ROOT_CA_FILE` | `String` | `AmazonRootCA1.pem` | Nazwa pliku certyfikatu CA. |
| `LOG_LEVEL` | `String` | `INFO` | Poziom logowania (`DEBUG`, `INFO`, `WARN`, `ERROR`). |

---

## 5. Schemat Wiadomości MQTT (Data Payload)

Po zeskanowaniu kodu QR usługa publikuje wiadomość w następującym formacie JSON:

```json
{
  "event_id": "uuid4-generated-id",
  "client_id": "rpi-qr-scanner-01",
  "timestamp": 1722590000,
  "payload": {
    "raw_data": "https://example.com/qr-code-content",
    "encoding": "utf-8"
  }
}

```

---

## 6. Wymagania Niefunkcjonalne (Non-Functional Requirements)

* **NFR-01: Reliability & Resilience**
* Urządzenie musi automatycznie ponawiać próbę połączenia z serwerem AWS IoT w przypadku utraty połączenia internetowego (Exponential Backoff).
* Aplikacja wewnątrz kontenera musi podtrzymywać pętlę zdarzeń i nie ulegać awarii (crash) w przypadku odczytu niepoprawnie zakodowanych znaków z portu szeregowego.


* **NFR-02: Security**
* Brak poświadczeń AWS IAM (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) w kontenerze.
* Montowanie certyfikatów do kontenera wyłącznie w trybie **Tylko do odczytu (`ro`)**.


* **NFR-03: Performance & Resource Footprint**
* Użycie obrazu bazowego `python:3.11-slim` lub `alpine` w celu zminimalizowania rozmiaru obrazu Dockerowego.
* Użycie zasobów CPU na Raspberry Pi w stanie bezczynności: `< 2%`.



---

## 7. Przykład Wdrożeniowy (Deployment Artifacts)

### `docker-compose.yml`

```yaml
version: '3.8'

services:
  qr-scanner-engine:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: qr_scanner_service
    restart: always
    env_file:
      - .env
    devices:
      # Mapowanie fizycznego portu na port zdefiniowany w pliku .env
      - "${HOST_SERIAL_PORT:-/dev/ttyACM0}:${SERIAL_PORT:-/dev/ttyACM0}"
    volumes:
      # Montowanie lokalnego katalogu z certyfikatami w trybie Read-Only
      - ${HOST_CERTS_DIR:-./certs}:${AWS_CERT_DIR:-/app/certs}:ro

```

### Plik `.env` (Przykład konfiguracji)

```env
# Serial settings
HOST_SERIAL_PORT=/dev/ttyACM0
SERIAL_PORT=/dev/ttyACM0
SERIAL_BAUDRATE=9600

# AWS IoT settings
AWS_IOT_ENDPOINT=a3xyz123456789-ats.iot.eu-central-1.amazonaws.com
AWS_IOT_CLIENT_ID=kielce-office-scanner-01
AWS_IOT_TOPIC=factory/scanners/line1/qr

# Certs paths
HOST_CERTS_DIR=./certs
AWS_CERT_DIR=/app/certs
AWS_CERT_FILE=device.pem.crt
AWS_KEY_FILE=private.pem.key
AWS_ROOT_CA_FILE=AmazonRootCA1.pem

LOG_LEVEL=DEBUG

```

---

## 8. Kryteria Akceptacji (Acceptance Criteria)

1. **Test Zimnego Startu:** Po uruchomieniu `docker compose up -d` aplikacja automatycznie wczytuje zmienne, łączy się z AWS IoT Core i oczekuje na zdarzenia bez błędów w logach.
2. **Test Skanowania:** Zeskanowanie dowolnego kodu QR (tekst, URL, znak specjalny) generuje nowy wpis na wybranym temacie w konsole **AWS IoT Test Client**.
3. **Test Odłączenia Kabla USB:** Odłączenie i ponowne podpięcie skanera USB nie wymaga restartowania kontenera Docker – usługa samodzielnie odnawia połączenie z portem szeregowym.
4. **Test Odłączenia Sieci:** Zanik internetu i jego powrót powoduje automatyczne odnowienie sesji MQTT.