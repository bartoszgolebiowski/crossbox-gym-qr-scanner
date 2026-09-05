import argparse
import json
import logging
import os
import re
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


def fetch_ssm_parameter(param_name: str, region_name: str = "eu-central-1") -> Optional[str]:
    """Fetches a parameter string value from AWS SSM Parameter Store."""
    if not BOTO3_AVAILABLE:
        return None
    try:
        session = boto3.session.Session()
        client = session.client(service_name="ssm", region_name=region_name)
        response = client.get_parameter(Name=param_name, WithDecryption=False)
        return response.get("Parameter", {}).get("Value")
    except Exception as exc:
        logger.warning("Could not fetch SSM parameter '%s': %s", param_name, exc)
        return None


def extract_device_data(secret_data: Dict[str, Any], thing_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts device certificate dictionary.
    Handles flat dictionaries as well as multi-device secret dictionaries.
    """
    # 1. Flat dictionary containing certificate_pem
    if "certificate_pem" in secret_data:
        return secret_data

    # 2. Match explicitly requested thing_name
    if thing_name and thing_name in secret_data:
        device_entry = secret_data[thing_name]
        if isinstance(device_entry, dict):
            return device_entry

    # 3. Match known default thing names
    candidate_names = ["crossbox-qr-scanner-01", "crossbox-qr-scanner"]
    for candidate in candidate_names:
        if candidate in secret_data and isinstance(secret_data[candidate], dict):
            logger.info("Found credentials matching device key: '%s'", candidate)
            return secret_data[candidate]

    # 4. Search for any key containing 'scanner'
    for key, val in secret_data.items():
        if "scanner" in key.lower() and isinstance(val, dict) and "certificate_pem" in val:
            logger.info("Auto-selected device credentials from key: '%s'", key)
            return val

    # 5. If only one device dict exists, use it
    dict_keys = [k for k, v in secret_data.items() if isinstance(v, dict) and "certificate_pem" in v]
    if len(dict_keys) == 1:
        logger.info("Using device credentials from sole device key: '%s'", dict_keys[0])
        return secret_data[dict_keys[0]]

    raise ValueError(
        f"Device credentials for '{thing_name or 'scanner'}' not found in secret. Available keys: {list(secret_data.keys())}"
    )


def save_certificates(
    secret_data: Dict[str, Any],
    output_dir: Path,
    thing_name: Optional[str] = None,
    cert_name: str = "certificate.pem.crt",
    key_name: str = "private.pem.key",
    ca_name: str = "AmazonRootCA1.pem",
    endpoint_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Saves certificate PEM, private key, Root CA, and config metadata to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    device_data = extract_device_data(secret_data, thing_name)

    cert_path = output_dir / cert_name
    key_path = output_dir / key_name
    ca_path = output_dir / ca_name
    config_path = output_dir / "config.json"

    if "certificate_pem" in device_data:
        cert_path.write_text(device_data["certificate_pem"], encoding="utf-8")
        # Also write device.pem.crt for dual compatibility with .env and tests
        alt_cert_path = output_dir / ("device.pem.crt" if cert_name != "device.pem.crt" else "certificate.pem.crt")
        alt_cert_path.write_text(device_data["certificate_pem"], encoding="utf-8")

    if "private_key" in device_data:
        key_path.write_text(device_data["private_key"], encoding="utf-8")
        try:
            # Set read/write only for owner on POSIX systems (Linux/Raspberry Pi)
            key_path.chmod(0o600)
        except Exception:
            pass

    if "root_ca" in device_data:
        ca_path.write_text(device_data["root_ca"], encoding="utf-8")

    endpoint = endpoint_override or device_data.get("endpoint_address", device_data.get("endpoint", ""))
    resolved_thing_name = thing_name or device_data.get("thing_name", "crossbox-qr-scanner-01")

    config_data = {
        "thing_name": resolved_thing_name,
        "endpoint": endpoint,
        "endpoint_address": endpoint,
        "certificate_arn": device_data.get("certificate_arn", ""),
        "certificate_id": device_data.get("certificate_id", ""),
    }
    config_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    logger.info("Certificates successfully saved to %s", output_dir)

    return {
        "endpoint": endpoint,
        "thing_name": resolved_thing_name,
        "certificate_arn": device_data.get("certificate_arn", ""),
        "certificate_id": device_data.get("certificate_id", ""),
        "cert_path": str(cert_path),
        "key_path": str(key_path),
        "ca_path": str(ca_path),
    }


def update_env_file(
    env_file: Path,
    endpoint: str,
    thing_name: str,
    region: str = "eu-central-1",
    serial_port: Optional[str] = None,
    host_serial_port: Optional[str] = None,
) -> None:
    """Updates or generates .env file with current AWS IoT endpoints and credentials."""
    env_updates = {
        "AWS_IOT_ENDPOINT": endpoint,
        "AWS_IOT_CLIENT_ID": thing_name,
        "AWS_IOT_TOPIC": f"gym/scanners/{thing_name}/scan",
        "AWS_IOT_HEARTBEAT_TOPIC": f"gym/devices/{thing_name}/heartbeat",
        "AWS_REGION": region,
        "AWS_SECRET_NAME": "crossbox-gym/iot/certs",
        "AWS_CERT_DIR": "/app/certs",
        "HOST_CERTS_DIR": "./certs",
        "AWS_CERT_FILE": "device.pem.crt",
        "AWS_KEY_FILE": "private.pem.key",
        "AWS_ROOT_CA_FILE": "AmazonRootCA1.pem",
    }
    if serial_port:
        env_updates["SERIAL_PORT"] = serial_port
    if host_serial_port:
        env_updates["HOST_SERIAL_PORT"] = host_serial_port

    existing_lines = []
    found_keys = set()

    if env_file.exists():
        existing_lines = env_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _ = stripped.split("=", 1)
                key = key.strip()
                if key in env_updates:
                    new_lines.append(f"{key}={env_updates[key]}")
                    found_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # Append any missing keys
        missing_keys = [k for k in env_updates if k not in found_keys]
        if missing_keys:
            new_lines.append("")
            new_lines.append("# Added by fetch_certs.py configuration update")
            for k in missing_keys:
                new_lines.append(f"{k}={env_updates[k]}")

        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        logger.info("Updated existing .env configuration at %s", env_file)
    else:
        # Create new .env file with default template
        template_file = env_file.parent / ".env.example"
        if template_file.exists():
            content = template_file.read_text(encoding="utf-8")
            for k, v in env_updates.items():
                pattern = re.compile(rf"^{k}=.*$", re.MULTILINE)
                if pattern.search(content):
                    content = pattern.sub(f"{k}={v}", content)
                else:
                    content += f"\n{k}={v}"
            env_file.write_text(content.strip() + "\n", encoding="utf-8")
        else:
            lines = [f"{k}={v}" for k, v in env_updates.items()]
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Created new .env file at %s", env_file)


def main():
    parser = argparse.ArgumentParser(description="Fetch mTLS certificates from AWS Secrets Manager & SSM")
    parser.add_argument("-s", "--secret-name", default=os.getenv("AWS_SECRET_NAME", "crossbox-gym/iot/certs"), help="AWS Secrets Manager Secret Name")
    parser.add_argument("-t", "--thing-name", default=os.getenv("AWS_IOT_CLIENT_ID", "crossbox-qr-scanner-01"), help="IoT Thing Name")
    parser.add_argument("-r", "--region", default=os.getenv("AWS_REGION", "eu-central-1"), help="AWS Region")
    parser.add_argument("-o", "--output", default="./certs", help="Output directory for certificates")
    parser.add_argument("-e", "--endpoint", default=os.getenv("AWS_IOT_ENDPOINT"), help="Override AWS IoT ATS Endpoint")
    parser.add_argument("--update-env", action="store_true", help="Update .env with retrieved endpoint and thing details")
    parser.add_argument("--env-file", default=".env", help="Path to .env file to update")
    parser.add_argument("--serial-port", default=None, help="Serial port to set in .env (e.g. /dev/ttyACM0)")

    args = parser.parse_args()

    if not args.secret_name:
        logger.error("AWS Secret Name is required. Pass --secret-name or set AWS_SECRET_NAME env var.")
        sys.exit(1)

    try:
        # Determine endpoint: CLI arg -> SSM parameter -> Secret value
        endpoint = args.endpoint
        if not endpoint or "your-ats-endpoint" in endpoint:
            ssm_endpoint = fetch_ssm_parameter("/crossbox/iot/endpoint", args.region)
            if ssm_endpoint:
                logger.info("Retrieved endpoint from SSM /crossbox/iot/endpoint: %s", ssm_endpoint)
                endpoint = ssm_endpoint

        # Determine thing name: CLI arg -> SSM parameter -> Default
        thing_name = args.thing_name
        if not thing_name:
            ssm_thing = fetch_ssm_parameter("/crossbox/iot/scanner-thing-name", args.region)
            if ssm_thing:
                thing_name = ssm_thing
        thing_name = thing_name or "crossbox-qr-scanner-01"

        logger.info("Fetching secret '%s' from region '%s' for device '%s'...", args.secret_name, args.region, thing_name)
        secret_data = fetch_secret(args.secret_name, args.region)

        metadata = save_certificates(
            secret_data=secret_data,
            output_dir=Path(args.output),
            thing_name=thing_name,
            endpoint_override=endpoint,
        )

        final_endpoint = metadata.get("endpoint") or endpoint
        if not final_endpoint:
            logger.warning("IoT Endpoint was not found in secret or SSM. Please verify endpoint configuration.")

        if args.update_env:
            update_env_file(
                env_file=Path(args.env_file),
                endpoint=final_endpoint,
                thing_name=metadata.get("thing_name", thing_name),
                region=args.region,
                serial_port=args.serial_port,
                host_serial_port=args.serial_port,
            )

        print("\n" + "=" * 60)
        print("  AWS IoT Certificate Provisioning Complete")
        print("=" * 60)
        print(f"  Thing Name:      {metadata.get('thing_name')}")
        print(f"  IoT ATS Endpoint:{final_endpoint}")
        print(f"  Certificate ID:  {metadata.get('certificate_id')}")
        print(f"  Certificates Dir:{Path(args.output).resolve()}")
        print("=" * 60 + "\n")

    except Exception as exc:
        logger.error("Failed to fetch certificates: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
