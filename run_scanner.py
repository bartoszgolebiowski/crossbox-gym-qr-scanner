#!/usr/bin/env python3
"""
Crossbox Gym QR Scanner - Device Provisioning & Docker Runner
Collects mTLS certificates from AWS, sets IoT ATS endpoint in .env,
and launches the QR scanner service in Docker.
"""

import argparse
import glob
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RunScanner")

# Constants & Defaults
DEFAULT_SECRET_NAME = "crossbox-gym/iot/certs"
DEFAULT_THING_NAME = "crossbox-qr-scanner-01"
DEFAULT_REGION = "eu-central-1"
DEFAULT_SSM_ENDPOINT_PARAM = "/crossbox/iot/endpoint"
DEFAULT_SSM_THING_PARAM = "/crossbox/iot/scanner-thing-name"
DEFAULT_CERTS_DIR = "./certs"
DEFAULT_ENV_FILE = ".env"

PROJECT_ROOT = Path(__file__).resolve().parent


def check_dependencies() -> None:
    """Ensures boto3 is installed, attempting auto-install if missing."""
    try:
        import boto3  # noqa: F401
    except ImportError:
        logger.warning("boto3 is not installed. Attempting to install boto3 via pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "boto3"])
            logger.info("boto3 installed successfully.")
        except Exception as exc:
            logger.error("Failed to install boto3 automatically: %s", exc)
            logger.error("Please run: pip install boto3")
            sys.exit(1)


def check_docker() -> str:
    """Verifies Docker daemon and compose availability, returns compose command prefix."""
    if not shutil.which("docker"):
        logger.error("Docker executable not found in PATH!")
        logger.error("Install Docker on Raspberry Pi with: curl -fsSL https://get.docker.com | sh")
        sys.exit(1)

    # Check Docker daemon connectivity
    res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        logger.error("Cannot connect to Docker daemon. Is Docker running?")
        logger.error("On Linux/Raspberry Pi, ensure your user is in docker group: sudo usermod -aG docker $USER")
        sys.exit(1)

    # Check for 'docker compose' plugin or fallback to 'docker-compose'
    res = subprocess.run(["docker", "compose", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode == 0:
        return "docker compose"

    if shutil.which("docker-compose"):
        return "docker-compose"

    logger.error("Docker Compose not found. Please install docker-compose or docker-compose-plugin.")
    sys.exit(1)


def detect_serial_port(configured_port: Optional[str] = None) -> str:
    """Detects physical USB scanner port on Linux/Raspberry Pi or Windows."""
    if configured_port and (os.path.exists(configured_port) or sys.platform == "win32"):
        logger.info("Using user-specified serial port: %s", configured_port)
        return configured_port

    if sys.platform != "win32":
        # Search common Linux serial patterns
        patterns = ["/dev/ttyACM*", "/dev/ttyUSB*"]
        found_ports: List[str] = []
        for pat in patterns:
            found_ports.extend(glob.glob(pat))

        if found_ports:
            selected_port = found_ports[0]
            logger.info("Auto-detected physical USB scanner on: %s", selected_port)
            return selected_port

        logger.warning("No physical USB scanner detected on /dev/ttyACM* or /dev/ttyUSB*.")
        logger.warning("If testing without hardware, specify --mock to run in simulation mode.")
        return "/dev/ttyACM0"
    else:
        # On Windows, default to COM1 or dummy device
        return configured_port or "COM1"


def fetch_aws_secret(secret_name: str, region_name: str) -> Dict[str, Any]:
    """Retrieves secret data from AWS Secrets Manager."""
    import boto3
    logger.info("Connecting to AWS Secrets Manager (%s, secret='%s')...", region_name, secret_name)
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)

    if "SecretString" in response:
        return json.loads(response["SecretString"])
    return json.loads(response["SecretBinary"].decode("utf-8"))


def fetch_ssm_param(param_name: str, region_name: str) -> Optional[str]:
    """Retrieves string value from AWS SSM Parameter Store."""
    import boto3
    try:
        session = boto3.session.Session()
        client = session.client(service_name="ssm", region_name=region_name)
        response = client.get_parameter(Name=param_name, WithDecryption=False)
        return response.get("Parameter", {}).get("Value")
    except Exception as exc:
        logger.debug("SSM parameter lookup for '%s' failed: %s", param_name, exc)
        return None


def extract_device_credentials(secret_data: Dict[str, Any], thing_name: str) -> Dict[str, Any]:
    """Extracts target device credentials dictionary from secret payload."""
    # Flat dictionary containing certificate_pem directly
    if "certificate_pem" in secret_data:
        return secret_data

    # Nested dictionary with thing_name as key
    if thing_name in secret_data and isinstance(secret_data[thing_name], dict):
        return secret_data[thing_name]

    # Search for keys containing 'scanner'
    for k, v in secret_data.items():
        if "scanner" in k.lower() and isinstance(v, dict) and "certificate_pem" in v:
            logger.info("Selected credentials under matched key '%s'", k)
            return v

    raise ValueError(f"No credentials found for device '{thing_name}' in secret. Keys: {list(secret_data.keys())}")


def save_certificates(
    device_data: Dict[str, Any],
    output_dir: Path,
    endpoint: str,
    thing_name: str,
) -> None:
    """Saves certificates and writes config.json metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)

    cert_pem = device_data.get("certificate_pem")
    priv_key = device_data.get("private_key")
    root_ca = device_data.get("root_ca")

    if not cert_pem or not priv_key:
        raise ValueError("Secret payload is missing certificate_pem or private_key!")

    # Write device certificate (both device.pem.crt and certificate.pem.crt for compatibility)
    (output_dir / "device.pem.crt").write_text(cert_pem, encoding="utf-8")
    (output_dir / "certificate.pem.crt").write_text(cert_pem, encoding="utf-8")

    # Write private key with secure file permissions on Linux
    key_path = output_dir / "private.pem.key"
    key_path.write_text(priv_key, encoding="utf-8")
    try:
        key_path.chmod(0o600)
    except Exception:
        pass

    # Write Root CA
    if root_ca:
        (output_dir / "AmazonRootCA1.pem").write_text(root_ca, encoding="utf-8")

    # Write config metadata
    config_data = {
        "thing_name": thing_name,
        "endpoint": endpoint,
        "endpoint_address": endpoint,
        "certificate_arn": device_data.get("certificate_arn", ""),
        "certificate_id": device_data.get("certificate_id", ""),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (output_dir / "config.json").write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    logger.info("Successfully saved mTLS certificates to '%s'", output_dir.resolve())


def update_env_configuration(
    env_file_path: Path,
    endpoint: str,
    thing_name: str,
    region: str,
    serial_port: str,
    mock_serial: bool = False,
) -> None:
    """Creates or updates .env with ATS endpoint and IoT settings."""
    env_map = {
        "AWS_IOT_ENDPOINT": endpoint,
        "AWS_IOT_CLIENT_ID": thing_name,
        "AWS_IOT_TOPIC": f"gym/scanners/{thing_name}/scan",
        "AWS_IOT_HEARTBEAT_TOPIC": f"gym/devices/{thing_name}/heartbeat",
        "AWS_IOT_HEARTBEAT_INTERVAL_SECONDS": "10",
        "AWS_REGION": region,
        "AWS_SECRET_NAME": DEFAULT_SECRET_NAME,
        "HOST_SERIAL_PORT": serial_port,
        "SERIAL_PORT": serial_port,
        "SERIAL_BAUDRATE": "9600",
        "HOST_CERTS_DIR": "./certs",
        "AWS_CERT_DIR": "/app/certs",
        "AWS_CERT_FILE": "device.pem.crt",
        "AWS_KEY_FILE": "private.pem.key",
        "AWS_ROOT_CA_FILE": "AmazonRootCA1.pem",
        "MOCK_SERIAL": "true" if mock_serial else "false",
        "LOG_LEVEL": "INFO",
    }

    if env_file_path.exists():
        lines = env_file_path.read_text(encoding="utf-8").splitlines()
        new_lines: List[str] = []
        handled_keys = set()

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _ = stripped.split("=", 1)
                k = k.strip()
                # Preserve existing custom values for logging or baudrate
                if k in ("LOG_LEVEL", "SERIAL_BAUDRATE") and line.strip():
                    new_lines.append(line)
                    handled_keys.add(k)
                elif k in env_map:
                    new_lines.append(f"{k}={env_map[k]}")
                    handled_keys.add(k)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        missing = [k for k in env_map if k not in handled_keys]
        if missing:
            new_lines.append("")
            new_lines.append("# Generated by run_scanner.py")
            for k in missing:
                new_lines.append(f"{k}={env_map[k]}")

        env_file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        logger.info("Updated existing configuration in '%s'", env_file_path)
    else:
        template = PROJECT_ROOT / ".env.example"
        if template.exists():
            content = template.read_text(encoding="utf-8")
            for k, v in env_map.items():
                content = re.sub(rf"^{k}=.*$", f"{k}={v}", content, flags=re.MULTILINE)
            env_file_path.write_text(content.strip() + "\n", encoding="utf-8")
        else:
            lines = [f"{k}={v}" for k, v in env_map.items()]
            env_file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Created new configuration file '%s'", env_file_path)


def run_docker_service(compose_cmd: str, build: bool = True, follow_logs: bool = True) -> None:
    """Builds, starts, and verifies the Docker Compose service."""
    parts = compose_cmd.split()

    # 1. Stop any existing container
    logger.info("Stopping any existing scanner container...")
    subprocess.run(parts + ["down"], cwd=PROJECT_ROOT, check=False)

    # 2. Build image if requested
    if build:
        logger.info("Building Docker image for scanner engine...")
        build_res = subprocess.run(parts + ["build"], cwd=PROJECT_ROOT)
        if build_res.returncode != 0:
            logger.error("Docker build failed!")
            sys.exit(1)

    # 3. Start container in detached mode
    logger.info("Starting QR Scanner service container in detached mode...")
    up_res = subprocess.run(parts + ["up", "-d"], cwd=PROJECT_ROOT)
    if up_res.returncode != 0:
        logger.error("Docker up failed!")
        sys.exit(1)

    # 4. Wait a few seconds for initialization
    logger.info("Waiting 4 seconds for service to initialize and connect to AWS...")
    time.sleep(4)

    # 5. Display status
    subprocess.run(parts + ["ps"], cwd=PROJECT_ROOT)

    # 6. Check logs for AWS connection
    log_check = subprocess.run(
        parts + ["logs", "qr-scanner-engine", "--tail=40"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    logs_output = log_check.stdout

    print("\n" + "-" * 60)
    print(logs_output.strip())
    print("-" * 60 + "\n")

    if "Successfully connected to AWS IoT Core" in logs_output:
        logger.info("VERIFICATION PASSED: QR Scanner is CONNECTED to AWS IoT Core!")
    else:
        logger.warning("Connection confirmation not yet visible in initial logs. Checking...")

    if follow_logs:
        logger.info("Streaming container logs (Press Ctrl+C to exit log view, container remains running)...")
        try:
            subprocess.run(parts + ["logs", "-f", "qr-scanner-engine"], cwd=PROJECT_ROOT)
        except KeyboardInterrupt:
            logger.info("Exited log follow mode. Container is still running in background.")


def main():
    parser = argparse.ArgumentParser(
        description="Crossbox Gym QR Scanner - AWS Certificate Collector & Docker Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-s", "--secret-name", default=DEFAULT_SECRET_NAME, help="AWS Secrets Manager secret name")
    parser.add_argument("-t", "--thing-name", default=DEFAULT_THING_NAME, help="AWS IoT Thing Name")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION, help="AWS Region")
    parser.add_argument("-e", "--endpoint", default=None, help="Explicit AWS IoT ATS Endpoint URL override")
    parser.add_argument("-p", "--port", default=None, help="Host serial port (e.g. /dev/ttyACM0 or COM3)")
    parser.add_argument("-o", "--certs-dir", default=DEFAULT_CERTS_DIR, help="Directory to save certificates")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Path to .env file to update")
    parser.add_argument("--mock", action="store_true", help="Enable mock serial mode for testing without hardware")
    parser.add_argument("--no-build", action="store_true", help="Skip Docker image rebuild")
    parser.add_argument("--no-logs", action="store_true", help="Do not attach and follow logs after starting")

    args = parser.parse_args()

    print("=" * 68)
    print("      Crossbox Gym QR Scanner - AWS IoT Edge Docker Runner         ")
    print("=" * 68)

    # 1. Dependency checks
    check_dependencies()
    compose_cmd = check_docker()
    logger.info("Using compose command: '%s'", compose_cmd)

    # 2. Hardware / Port detection
    detected_port = detect_serial_port(args.port)
    if args.mock:
        logger.info("Mock serial stream enabled via --mock flag.")

    # 3. Collect certificates and endpoint from AWS
    try:
        secret_data = fetch_aws_secret(args.secret_name, args.region)
        device_data = extract_device_credentials(secret_data, args.thing_name)
    except Exception as exc:
        logger.error("Failed to retrieve secret from AWS: %s", exc)
        logger.error("Please verify AWS credentials (AWS_ACCESS_KEY_ID or ~/.aws/credentials).")
        sys.exit(1)

    # Determine endpoint: CLI arg -> SSM parameter -> Secret value
    endpoint = args.endpoint
    if not endpoint:
        ssm_endpoint = fetch_ssm_param(DEFAULT_SSM_ENDPOINT_PARAM, args.region)
        if ssm_endpoint:
            logger.info("Retrieved ATS Endpoint from SSM '%s': %s", DEFAULT_SSM_ENDPOINT_PARAM, ssm_endpoint)
            endpoint = ssm_endpoint
        else:
            endpoint = device_data.get("endpoint_address", device_data.get("endpoint"))

    if not endpoint:
        logger.error("Could not determine AWS IoT Endpoint! Specify via --endpoint.")
        sys.exit(1)

    # 4. Save certificate files
    certs_dir = Path(args.certs_dir)
    save_certificates(
        device_data=device_data,
        output_dir=certs_dir,
        endpoint=endpoint,
        thing_name=args.thing_name,
    )

    # 5. Update .env configuration
    env_file = Path(args.env_file)
    update_env_configuration(
        env_file_path=env_file,
        endpoint=endpoint,
        thing_name=args.thing_name,
        region=args.region,
        serial_port=detected_port,
        mock_serial=args.mock,
    )

    print("\n" + "=" * 68)
    print("  Provisioning Summary:")
    print(f"  • Thing Name:       {args.thing_name}")
    print(f"  • ATS Data Endpoint:{endpoint}")
    print(f"  • Serial Device:    {detected_port} (Mock: {args.mock})")
    print(f"  • Certificates Dir: {certs_dir.resolve()}")
    print(f"  • Environment File: {env_file.resolve()}")
    print("=" * 68 + "\n")

    # 6. Run Docker Compose
    run_docker_service(
        compose_cmd=compose_cmd,
        build=not args.no_build,
        follow_logs=not args.no_logs,
    )


if __name__ == "__main__":
    main()
