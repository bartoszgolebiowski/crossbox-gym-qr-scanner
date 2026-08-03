import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("FetchCerts")

try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


def fetch_secret(secret_name: str, region_name: str = "eu-central-1") -> Dict[str, Any]:
    """Fetches certificate secret JSON from AWS Secrets Manager."""
    if not BOTO3_AVAILABLE:
        raise RuntimeError("boto3 package is required to fetch certificates from AWS Secrets Manager.")
    
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)
    
    if "SecretString" in response:
        return json.loads(response["SecretString"])
    else:
        return json.loads(response["SecretBinary"].decode("utf-8"))


def save_certificates(
    secret_data: Dict[str, Any],
    output_dir: Path,
    cert_name: str = "certificate.pem.crt",
    key_name: str = "private.pem.key",
    ca_name: str = "AmazonRootCA1.pem",
) -> None:
    """Saves certificate PEM, private key, Root CA, and config metadata to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    cert_path = output_dir / cert_name
    key_path = output_dir / key_name
    ca_path = output_dir / ca_name
    config_path = output_dir / "config.json"

    if "certificate_pem" in secret_data:
        cert_path.write_text(secret_data["certificate_pem"], encoding="utf-8")
    if "private_key" in secret_data:
        key_path.write_text(secret_data["private_key"], encoding="utf-8")
    if "root_ca" in secret_data:
        ca_path.write_text(secret_data["root_ca"], encoding="utf-8")

    config_data = {
        "endpoint": secret_data.get("endpoint_address", secret_data.get("endpoint", "")),
        "certificate_arn": secret_data.get("certificate_arn", ""),
        "certificate_id": secret_data.get("certificate_id", ""),
    }
    config_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    logger.info("Certificates successfully saved to %s", output_dir)


def main():
    parser = argparse.ArgumentParser(description="Fetch mTLS certificates from AWS Secrets Manager")
    parser.add_argument("-s", "--secret-name", default=os.getenv("AWS_SECRET_NAME"), help="AWS Secrets Manager Secret Name")
    parser.add_argument("-r", "--region", default=os.getenv("AWS_REGION", "eu-central-1"), help="AWS Region")
    parser.add_argument("-o", "--output", default="./certs", help="Output directory for certificates")

    args = parser.parse_args()

    if not args.secret_name:
        logger.error("AWS Secret Name is required. Pass --secret-name or set AWS_SECRET_NAME env var.")
        sys.exit(1)

    try:
        secret_data = fetch_secret(args.secret_name, args.region)
        save_certificates(secret_data, Path(args.output))
    except Exception as exc:
        logger.error("Failed to fetch certificates: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
