"""Provision a coach password without putting it on argv or printing it."""
import getpass
import os
from pathlib import Path

from app.services.commerce.auth import password_hash


def main():
    first = getpass.getpass("New coach password (16+ characters): ")
    second = getpass.getpass("Repeat password: ")
    if first != second or len(first) < 16:
        raise SystemExit("Passwords must match and contain at least 16 characters. No changes made.")
    target = Path(__file__).resolve().parents[2] / ".env"
    lines = target.read_text().splitlines() if target.exists() else []
    lines = [line for line in lines if not line.startswith("COACH_PASSWORD_HASH=")]
    # Quote the hash for dotenv; dollars are literal and not shell-expanded here.
    lines.append("COACH_PASSWORD_HASH='" + password_hash(first) + "'")
    target.write_text("\n".join(lines) + "\n")
    os.chmod(target, 0o600)
    print("Coach password hash saved to this copy’s .env. Restart the API. Share the password privately.")


if __name__ == "__main__":
    main()
