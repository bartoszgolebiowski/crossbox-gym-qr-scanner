# Crossbox Gym QR Scanner — Raspberry Pi Installation & Deployment Guide

Kompletny przewodnik instalacji, konfiguracji sprzętowej oraz uruchomienia produkcyjnego usługi **Crossbox Gym QR Scanner** na urządzeniu **Raspberry Pi** z wykorzystaniem kontenerów **Docker** i chmury **AWS IoT Core**.

---

## 📋 Spis Treści

1. [Wymagania Sprzętowe i Systemowe](#1-wymagania-sprzętowe-i-systemowe)
2. [Wymagania AWS (IAM & Uprawnienia)](#2-wymagania-aws-iam--uprawnienia)
3. [Konfiguracja Fizycznego Skanera (HDWR-HD360)](#3-konfiguracja-fizycznego-skanera-hdwr-hd360)
4. [Przygotowanie Systemu na Raspberry Pi](#4-przygotowanie-systemu-na-raspberry-pi)
5. [Instalacja i Uruchomienie (Krok po Kroku)](#5-instalacja-i-uruchomienie-krok-po-kroku)
6. [Autostart Usługi po Reboocie (Systemd)](#6-autostart-usługi-po-reboocie-systemd)
7. [Weryfikacja Działania i Testy](#7-weryfikacja-działania-i-testy)
8. [Rozwiązywanie Problemów (Troubleshooting)](#8-rozwiązywanie-problemów-troubleshooting)

---

## 1. Wymagania Sprzętowe i Systemowe

| Komponent | Wymaganie minimalne / zalecane | Uwagi |
| :--- | :--- | :--- |
| **Urządzenie** | Raspberry Pi 3B+, 4B, 5 lub Zero 2W | Zalecane min. 1 GB RAM |
| **System Operacyjny** | Raspberry Pi OS (64-bit) / Debian 12 (Bookworm) | Wersja Lite (bez GUI) jest w zupełności wystarczająca |
| **Skaner QR** | **HDWR-HD360-QR-Scanner** (USB) | Wymaga pracy w trybie Virtual COM (Serial) |
| **Karta MicroSD** | Min. 16 GB, Class 10 / A1 | Dla stabilnej pracy Dockera |
| **Sieć** | Ethernet lub Wi-Fi 2.4/5 GHz | Wymagany ruch wychodzący na porty **443 (HTTPS)** i **8883 (MQTT mTLS)** |

---

## 2. Wymagania AWS (IAM & Uprawnienia)

Aby skrypt mógł automatycznie pobrać certyfikaty mTLS oraz parametry endpointu, Raspberry Pi musi posiadać uprawnienia AWS.

### Wymagana minimalna polityka IAM (dla usera / roli):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSecretsManagerRead",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:eu-central-1:*:secret:crossbox-gym/iot/certs*"
    },
    {
      "Sid": "AllowSSMParameterRead",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters"
      ],
      "Resource": "arn:aws:ssm:eu-central-1:*:parameter/crossbox/iot/*"
    }
  ]
}
```

### Zasoby w chmurze AWS wykorzystywane przez skrypt:
- **Secrets Manager**: `crossbox-gym/iot/certs` (zawiera klucz prywatny, certyfikat urządzenia oraz certyfikat Root CA Amazon).
- **SSM Parameter Store**:
  - `/crossbox/iot/endpoint` (np. `a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com`)
  - `/crossbox/iot/scanner-thing-name` (`crossbox-qr-scanner-01`)
- **Reguły AWS IoT Topic**:
  - Skanowanie: `gym/scanners/{client_id}/scan`
  - Heartbeat: `gym/devices/{client_id}/heartbeat`

---

## 3. Konfiguracja Fizycznego Skanera (HDWR-HD360)

Skaner kodów **HDWR HD360** domyślnie po podłączeniu do USB działa w trybie emulacji klawiatury (**USB HID Keyboard**). 

> [!IMPORTANT]
> Aplikacja wymaga, aby skaner pracował w trybie wirtualnego portu szeregowego (**USB Virtual COM / CDC-ACM**).

### Instrukcja przestawienia skanera:
1. Podłącz skaner kablem USB do Raspberry Pi lub komputera.
2. W papierowej instrukcji dołączonej do skanera HDWR HD360 odszukaj rozdział **"Communication Mode"** lub **"Interface Selection"**.
3. Zeskanuj kod kreskowy: **"USB Virtual COM"** (lub **"CDC-ACM Mode"**).
4. Skaner wyda charakterystyczny dźwięk potrójnego piknięcia i zrestartuje się jako urządzenie szeregowe.
5. Upewnij się, że włączona jest domyślna prędkość transmisji: **9600 baud, 8N1** oraz wysyłanie znaku nowej linii (`\r\n` / CR+LF) po każdym skanie.

### Weryfikacja w systemie Linux (Raspberry Pi):
Po podłączeniu skanera do USB uruchom w terminalu:
```bash
dmesg | grep -E "ttyACM|ttyUSB"
```
Powinieneś zobaczyć wpis podobny do:
```text
cdc_acm 1-1.2:1.0: ttyACM0: USB ACM device
```
lub
```text
ftdi_sio 1-1.2:1.0: ttyUSB0: FTDI USB Serial Device converter now attached to ttyUSB0
```

---

## 4. Przygotowanie Systemu na Raspberry Pi

Zaloguj się na Raspberry Pi przez SSH (`ssh pi@<ip_malinki>`) i wykonaj wstępną konfigurację:

### Krok 4.1: Aktualizacja systemu i synchronizacja czasu (NTP)
> [!WARNING]
> Certyfikaty mTLS wymagają precyzyjnego zegara systemowego. Jeśli data lub godzina na Raspberry Pi będzie nieprawidłowa, połączenie SSL/TLS z AWS IoT zostanie natychmiast odrzucone!

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3 python3-pip python3-venv

# Upewnij się, że czas jest zsynchronizowany:
sudo timedatectl set-ntp true
timedatectl status
```

### Krok 4.2: Instalacja Dockera i Docker Compose
Jeśli Docker nie jest jeszcze zainstalowany, skorzystaj z oficjalnego skryptu instalacyjnego:
```bash
curl -fsSL https://get.docker.com | sh

# Dodaj bieżącego użytkownika do grupy docker oraz dialout (dostęp do portów USB):
sudo usermod -aG docker $USER
sudo usermod -aG dialout $USER
```

> [!NOTE]
> Po dodaniu użytkownika do grup należy się wylogować i zalogować ponownie (`exit` i powtórne `ssh`), aby nowe uprawnienia zaczęły działać.

Sprawdź poprawność instalacji:
```bash
docker --version
docker compose version
```

### Krok 4.3: Konfiguracja AWS CLI / Poświadczeń
Zainstaluj AWS CLI lub skonfiguruj plik poświadczeń:
```bash
pip install awscli --break-system-packages 2>/dev/null || pip install awscli
aws configure
```
Podaj:
- **AWS Access Key ID**: `Twój klucz dostępu`
- **AWS Secret Access Key**: `Twój tajny klucz`
- **Default region name**: `eu-central-1`
- **Default output format**: `json`

*(Możesz również wyeksportować poświadczenia w zmiennych środowiskowych: `export AWS_ACCESS_KEY_ID=...` i `export AWS_SECRET_ACCESS_KEY=...`)*.

---

## 5. Instalacja i Uruchomienie (Krok po Kroku)

### Krok 5.1: Sklonowanie repozytorium
```bash
cd ~
git clone https://github.com/bartoszgolebiowski/crossbox-gym-qr-scanner.git
cd crossbox-gym-qr-scanner
```

### Krok 5.2: Uruchomienie skryptu instalacyjno-wdrożeniowego
Wystarczy uruchomić jeden dedykowany skrypt Python:

```bash
python3 run_scanner.py
```

### Co automatycznie wykona skrypt `run_scanner.py`?
1. **Weryfikacja środowiska**: sprawdza status demona Docker oraz uprawnienia do portu USB.
2. **Auto-detekcja portu USB**: skanuje `/dev/ttyACM*` oraz `/dev/ttyUSB*` i odnajduje fizyczny czytnik kodów QR.
3. **Pobranie mTLS z AWS**: łączy się z AWS Secrets Manager (`crossbox-gym/iot/certs`) i pobiera certyfikaty urządzenia `crossbox-qr-scanner-01`:
   - `certs/device.pem.crt`
   - `certs/private.pem.key` (z bezpiecznymi uprawnieniami `0600`)
   - `certs/AmazonRootCA1.pem`
4. **Pobranie endpointu ATS**: pobiera dedykowany endpoint z AWS SSM (`a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com`).
5. **Konfiguracja `.env`**: tworzy/aktualizuje konfigurację `.env` z parametrami brokera MQTT, tematami i ścieżką do portu szeregowego.
6. **Docker Compose**: buduje lekki kontener Python 3.11 i uruchamia go w tle z montowaniem wolumenu certyfikatów w trybie `:ro` (tylko do odczytu) oraz passthrough urządzenia USB (`/dev/ttyACM0`).
7. **Weryfikacja połączenia**: nasłuchuje logów startowych i potwierdza nawiązanie sesji mTLS z brokerem AWS IoT.

### Opcje zaawansowane skryptu `run_scanner.py`:
```bash
# Uruchomienie w trybie symulacji (bez fizycznego skanera):
python3 run_scanner.py --mock

# Uruchomienie w tle bez śledzenia logów na konsoli:
python3 run_scanner.py --no-logs

# Wymuszenie konkretnego portu USB (jeśli masz podłączonych kilka urządzeń):
python3 run_scanner.py -p /dev/ttyUSB0
```

---

## 6. Autostart Usługi po Reboocie (Systemd)

Aby usługa automatycznie podnosiła się po zaniku zasilania lub restarcie Raspberry Pi, skonfiguruj jednostkę `systemd`.

### Krok 6.1: Utwórz plik jednostki systemd
```bash
sudo nano /etc/systemd/system/crossbox-qr-scanner.service
```

Wklej poniższą konfigurację (dostosuj ścieżkę `/home/pi/...` jeśli Twój użytkownik ma inną nazwę):

```ini
[Unit]
Description=Crossbox Gym QR Scanner Docker Service
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=pi
WorkingDirectory=/home/pi/crossbox-gym-qr-scanner
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
```

### Krok 6.2: Włącz i aktywuj usługę
```bash
sudo systemctl daemon-reload
sudo systemctl enable crossbox-qr-scanner.service
sudo systemctl start crossbox-qr-scanner.service
```

### Krok 6.3: Sprawdź status usługi
```bash
sudo systemctl status crossbox-qr-scanner.service
```

---

## 7. Weryfikacja Działania i Testy

### 7.1. Sprawdzenie statusu kontenera
```bash
docker compose ps
```
Status kontenera powinien wynosić `Up` (np. `running`).

### 7.2. Podgląd logów w czasie rzeczywistym
```bash
docker compose logs -f qr-scanner-engine
```
W logach powinny pojawiać się cykliczne wpisy:
```text
[INFO] AWSIoTPublisher: Initializing AWS IoT connection to 'a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com'...
[INFO] AWSIoTPublisher: Successfully connected to AWS IoT Core.
[INFO] EngineMain: QRScannerEngine is fully operational.
[INFO] AWSIoTPublisher: Published message to 'gym/devices/crossbox-qr-scanner-01/heartbeat'
```

### 7.3. Test fizycznego skanu
1. Wyświetl na ekranie telefonu lub wydrukuj dowolny kod QR (np. z zawartością `https://crossboxgym.pl/checkin/member/12345`).
2. Skieruj kod na czytnik HDWR-HD360.
3. W logach kontenera natychmiast pojawi się:
```text
[INFO] EngineMain: QR Code captured: 'https://crossboxgym.pl/checkin/member/12345'. Adding to queue...
[INFO] AWSIoTPublisher: Published scan event ID: 4a2b1c8e-... to gym/scanners/crossbox-qr-scanner-01/scan
```
4. Wiadomość trafia do reguły AWS IoT `CrossboxQrScannerScanRule`, która wywołuje funkcję Lambda weryfikującą wejście klienta do klubu!

### 7.4. Ręczny test programowy (Trigger Test Scan)
Możesz również wywołać skan testowy ręcznie z poziomu konsoli bez użycia fizycznego skanera:
```bash
python3 scripts/trigger_scan.py --qr "TEST-MEMBER-9999"
```

---

## 8. Rozwiązywanie Problemów (Troubleshooting)

### Problem 1: `PermissionError: [Errno 13] Permission denied: '/dev/ttyACM0'`
- **Przyczyna**: Użytkownik uruchamiający kontener lub proces nie należy do grupy uprawnionej do portów szeregowych.
- **Rozwiązanie**:
  ```bash
  sudo usermod -aG dialout $USER
  sudo chmod 666 /dev/ttyACM0
  ```
  Zaloguj się ponownie do powłoki.

### Problem 2: `error gathering device information while adding custom device "/dev/ttyACM0": no such file or directory`
- **Przyczyna**: Skaner nie jest fizycznie wpięty do portu USB lub zgłosił się pod innym numerem (np. `/dev/ttyUSB0` lub `/dev/ttyACM1`).
- **Rozwiązanie**:
  1. Sprawdź faktyczną ścieżkę urządzenia: `ls -l /dev/ttyACM* /dev/ttyUSB*`
  2. Zaktualizuj zmienną w `.env`:
     ```env
     HOST_SERIAL_PORT=/dev/ttyUSB0
     SERIAL_PORT=/dev/ttyUSB0
     ```
  3. Zrestartuj kontener: `docker compose up -d`

### Problem 3: `awscrt.exceptions.AwsCrtError: AWS_IO_TLS_ERROR_NEGOTIATION_FAILURE`
- **Przyczyna**: Rozbieżność zegara Raspberry Pi lub nieprawidłowy endpoint/certyfikaty.
- **Rozwiązanie**:
  1. Zsynchronizuj czas zegara NTP:
     ```bash
     sudo timedatectl set-ntp true
     sudo systemctl restart systemd-timesyncd
     ```
  2. Upewnij się, że endpoint w `.env` to adres ATS: `a3djsvufxw89jd-ats.iot.eu-central-1.amazonaws.com`.
  3. Pobierz świeże certyfikaty:
     ```bash
     python3 scripts/fetch_certs.py -s crossbox-gym/iot/certs --update-env
     ```

### Problem 4: Skaner pika, ale kod nie pojawia się w logach
- **Przyczyna**: Skaner jest w trybie emulacji klawiatury (USB HID), a nie w trybie wirtualnego portu szeregowego (Virtual COM).
- **Rozwiązanie**: Zeskanuj kod kreskowy "USB Virtual COM" z instrukcji obsługi skanera HDWR HD360 (patrz Rozdział 3).

---

## 📞 Wsparcie i Utrzymanie

| Polecenie | Cel |
| :--- | :--- |
| `docker compose logs -f` | Śledzenie bieżącej pracy silnika skanera |
| `docker compose restart` | Szybki restart usługi bez usuwania wolumenów |
| `docker compose down` | Bezpieczne zatrzymanie kontenera |
| `docker compose pull && docker compose up -d --build` | Aktualizacja kontenera do najnowszej wersji kodu |
