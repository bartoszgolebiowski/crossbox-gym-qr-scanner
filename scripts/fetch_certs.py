#!/usr/bin/env python3
"""
AWS IoT Edge QR Scanner - Certificate Fetcher CLI.

Pobiera certyfikaty mTLS (certificate.pem.crt, private.pem.key, amazon-root-ca1.pem, config.json)
z AWS Secrets Manager i zapisuje je w zadanym katalogu.
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

# Load .env variables if python-dotenv is present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("FetchCerts")


def setup_logging(verbose: bool = False) -> None:
    """Configures console logging format and log level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%H:%M:%S"
    )


def fetch_from_secrets_manager(secret_name: str, region: str) -> dict:
    """Fetches a secret JSON object from AWS Secrets Manager using boto3."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.error("Pakiet 'boto3' nie jest zainstalowany. Zainstaluj go używając 'pip install boto3'.")
        sys.exit(1)

    print(f'[IoT Cert Fetcher] Fetching secret "{secret_name}"...')
    try:
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "Unknown")
        print(f"[IoT Cert Fetcher] Error fetching certificates: AWS Secrets Manager [{error_code}]: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"[IoT Cert Fetcher] Error fetching certificates: {err}", file=sys.stderr)
        sys.exit(1)

    raw_secret = response.get("SecretString")
    if not raw_secret:
        print("[IoT Cert Fetcher] Error fetching certificates: Secret value is empty", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(raw_secret)
    except json.JSONDecodeError:
        print("[IoT Cert Fetcher] Error fetching certificates: Secret string is not valid JSON", file=sys.stderr)
        sys.exit(1)


def fetch_amazon_root_ca() -> str:
    """Fetches official Amazon Root CA 1 certificate from Amazon Trust repository."""
    url = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
    logger.info("Downloading official Amazon Root CA 1 from %s...", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FetchCertsCLI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except Exception as err:
        print(f"[IoT Cert Fetcher] Error fetching certificates: Failed to download Root CA: {err}", file=sys.stderr)
        sys.exit(1)


def save_certificates(
    secret_data: dict,
    output_dir: Path,
    cert_name: str = "certificate.pem.crt",
    key_name: str = "private.pem.key",
    ca_name: str = "amazon-root-ca1.pem"
) -> None:
    """Saves certificates and config.json to output directory with default paths and secure file permissions."""
    output_dir.mkdir(parents=True, exist_ok=True)

    cert_pem = secret_data.get("certificate_pem") or secret_data.get("device.pem.crt") or secret_data.get("cert")
    key_pem = secret_data.get("private_key") or secret_data.get("private.pem.key") or secret_data.get("key")
    root_ca = secret_data.get("root_ca") or secret_data.get("AmazonRootCA1.pem") or secret_data.get("ca")

    if not cert_pem:
        print(f"[IoT Cert Fetcher] Error fetching certificates: Missing 'certificate_pem' field in secret", file=sys.stderr)
        sys.exit(1)

    if not key_pem:
        print(f"[IoT Cert Fetcher] Error fetching certificates: Missing 'private_key' field in secret", file=sys.stderr)
        sys.exit(1)

    if not root_ca:
        logger.info("Root CA field not found in secret. Downloading official Amazon Root CA 1...")
        root_ca = fetch_amazon_root_ca()

    cert_file = output_dir / cert_name
    key_file = output_dir / key_name
    ca_file = output_dir / ca_name
    config_file = output_dir / "config.json"

    cert_file.write_text(cert_pem, encoding="utf-8")
    key_file.write_text(key_pem, encoding="utf-8")
    ca_file.write_text(root_ca, encoding="utf-8")

    config_payload = {
        "endpoint": secret_data.get("endpoint_address"),
        "certificate_arn": secret_data.get("certificate_arn"),
        "certificate_id": secret_data.get("certificate_id"),
    }
    config_file.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

    # Set secure permissions (chmod 600 for private key) on Linux/macOS
    if os.name != "nt":
        try:
            os.chmod(key_file, 0o600)
            os.chmod(cert_file, 0o644)
            os.chmod(ca_file, 0o644)
            os.chmod(config_file, 0o644)
        except Exception as exc:
            logger.warning("Could not set chmod permissions: %s", exc)

    print(f"[IoT Cert Fetcher] Certificates saved successfully to: {output_dir}")
    print(f"- Certificate: {cert_file}")
    print(f"- Private Key: {key_file}")
    print(f"- Amazon Root CA: {ca_file}")
    print(f"- Config: {config_file}")


def main():
    default_secret = os.getenv("SECRET_NAME") or os.getenv("AWS_SECRET_NAME") or "hd360-qr-scanner/certs"
    default_region = os.getenv("AWS_REGION") or os.getenv("CDK_DEFAULT_REGION") or "eu-central-1"
    
    # Check command line arg for output dir
    cmd_output_dir = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    default_output_dir = cmd_output_dir or os.getenv("HOST_CERTS_DIR") or str(Path.cwd() / "certs")

    parser = argparse.ArgumentParser(
        description="Pobiera certyfikaty mTLS z AWS Secrets Manager i zapisuje je w domyślnych ścieżkach."
    )

    parser.add_argument(
        "-s", "--secret-name",
        default=default_secret,
        help=f"Nazwa lub ARN sekretu w AWS Secrets Manager (Domyślnie: '{default_secret}')"
    )
    parser.add_argument(
        "-r", "--region",
        default=default_region,
        help=f"Region AWS (Domyślnie: '{default_region}')"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=default_output_dir,
        help=f"Katalog docelowy (Domyślnie: '{default_output_dir}')"
    )
    parser.add_argument(
        "--cert-name",
        default=os.getenv("AWS_CERT_FILE", "certificate.pem.crt"),
        help="Nazwa pliku certyfikatu (Domyślnie: 'certificate.pem.crt')"
    )
    parser.add_argument(
        "--key-name",
        default=os.getenv("AWS_KEY_FILE", "private.pem.key"),
        help="Nazwa pliku klucza prywatnego (Domyślnie: 'private.pem.key')"
    )
    parser.add_argument(
        "--root-ca-name",
        default=os.getenv("AWS_ROOT_CA_FILE", "amazon-root-ca1.pem"),
        help="Nazwa pliku Root CA (Domyślnie: 'amazon-root-ca1.pem')"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Włącza szczegółowe logowanie DEBUG"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    output_path = Path(args.output_dir)
    secret_data = fetch_from_secrets_manager(args.secret_name, args.region)
    save_certificates(
        secret_data=secret_data,
        output_dir=output_path,
        cert_name=args.cert_name,
        key_name=args.key_name,
        ca_name=args.root_ca_name
    )


if __name__ == "__main__":
    main()
