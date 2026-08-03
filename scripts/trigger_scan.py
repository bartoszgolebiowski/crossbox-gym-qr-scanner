import argparse
import json
import logging
import sys
import urllib.request

logger = logging.getLogger("TriggerScan")


def trigger_scan_via_simulator(simulator_url: str, qr_data: str) -> bool:
    """Sends HTTP POST request to the Simulator API endpoint."""
    payload = json.dumps({"qr_data": qr_data}).encode("utf-8")
    req = urllib.request.Request(
        simulator_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                res_body = json.loads(resp.read().decode("utf-8"))
                event_id = res_body.get("event", {}).get("event_id", "N/A")
                logger.info("Successfully triggered scan event ID: %s", event_id)
                print(f"✅ QR Scan Published! Event ID: {event_id}")
                return True
            else:
                logger.error("Simulator API returned HTTP status: %d", resp.status)
                return False
    except Exception as exc:
        logger.error("Failed to trigger scan via simulator API: %s", exc)
        print(f"❌ Error triggering scan: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Manually trigger a QR code scan event via Simulator API")
    parser.add_argument(
        "-q", "--qr",
        default="https://crossboxgym.pl/checkin/member/12345",
        help="QR code raw text string or URL to publish"
    )
    parser.add_argument(
        "-u", "--url",
        default="http://localhost:8000/api/v1/scan",
        help="Simulator API endpoint URL"
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print(f"🚀 Triggering manual QR scan payload: '{args.qr}'...")
    success = trigger_scan_via_simulator(args.url, args.qr)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
