"""Hidden local input for Sandbox credentials. Never accepts or prints secret values on argv."""
import argparse
import getpass
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

from app.services.commerce.auth import password_hash

TARGET = Path(__file__).resolve().parents[2] / ".env"
KEYS = ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_MERCHANT_ID", "PAYPAL_WEBHOOK_ID", "COACH_PASSWORD_HASH")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report presence only; no provider request")
    args = parser.parse_args()
    current = dotenv_values(TARGET) if TARGET.exists() else {}
    if args.check:
        for key in KEYS:
            print(f"{key}: {'configured' if current.get(key) else 'missing'}")
        return
    if not sys.stdin.isatty():
        raise SystemExit("Run make paypal-setup in an interactive terminal so secret input stays hidden.")
    print("PayPal Sandbox only. Use the Business account's REST app, not a buyer password or legacy NVP credentials.")
    print("All input is hidden. Press Enter to retain a configured value. Webhook ID may be left empty until HTTPS exists.")
    updates = {}
    for key in KEYS[:-1]:
        value = getpass.getpass(f"{key}{' [configured]' if current.get(key) else ''}: ").strip()
        if value:
            if any(ch in value for ch in "\r\n'\" "):
                raise SystemExit("That value contains unsupported whitespace or quotes. No changes made.")
            updates[key] = value
    if not all(updates.get(k) or current.get(k) for k in KEYS[:3]):
        raise SystemExit("Client ID, client secret and merchant ID are required. No changes made.")
    if not current.get("COACH_PASSWORD_HASH"):
        first = getpass.getpass("Choose a private instructor password (16+ characters): ")
        second = getpass.getpass("Repeat instructor password: ")
        if len(first) < 16 or first != second:
            raise SystemExit("Passwords must match and contain at least 16 characters. No changes made.")
        updates["COACH_PASSWORD_HASH"] = password_hash(first)
    lines = TARGET.read_text().splitlines() if TARGET.exists() else []
    lines = [line for line in lines if line.split("=", 1)[0].strip() not in updates]
    lines.extend(f"{key}='{value}'" for key, value in updates.items())
    # Atomic replacement preserves unrelated settings and never leaves a partial credential file.
    temporary = TARGET.with_name(".env.sandbox-setup.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(temporary, TARGET)
        os.chmod(TARGET, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    print("Private Sandbox configuration saved. Restart the API; no provider request or payment was made.")


if __name__ == "__main__":
    main()
