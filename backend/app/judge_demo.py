"""Isolated judge walkthrough. Offline by default; Sandbox payments require --sandbox."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--reload", action="store_true", help="Reload the isolated development backend on source edits")
    parser.add_argument("--sandbox", action="store_true", help="Use configured PayPal Sandbox credentials for owned plans; synthetic purchases stay simulated")
    args = parser.parse_args()
    data = Path(__file__).resolve().parents[1] / "data-judge"
    values = {"APP_ENV": "development", "APP_MODE": "demo", "DATABASE_URL": f"sqlite:///{data / 'ghostrep-judge.db'}",
              "DATA_DIR": str(data), "FRONTEND_ORIGIN": "http://localhost:3110", "SESSION_COOKIE": "ghostrep_judge_athlete",
              "ENABLE_META_API": "false", "AI_PROVIDER": "local", "WORKOUT_PROVIDER": "local", "COACHING_PROVIDER": "local",
              "SEGMENTATION_PROVIDER": "none", "MODEL_API_KEY": "", "PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": "",
              "PAYPAL_MERCHANT_ID": "", "PAYPAL_WEBHOOK_ID": "", "COACH_PASSWORD_HASH": "", "COMMERCE_SIMULATOR_ENABLED": "true"}
    if args.sandbox:
        from app.config import Settings
        configured = Settings()
        if not configured.sandbox_configured:
            raise SystemExit("PayPal Sandbox credentials are missing. Run make paypal-setup first.")
        values.update(PAYPAL_CLIENT_ID=configured.paypal_client_id,
                      PAYPAL_CLIENT_SECRET=configured.paypal_client_secret,
                      PAYPAL_MERCHANT_ID=configured.paypal_merchant_id,
                      PAYPAL_WEBHOOK_ID=configured.paypal_webhook_id,
                      COACH_PASSWORD_HASH=configured.coach_password_hash)
    os.environ.update(values)
    if args.seed:
        from app.commerce_demo import main as seed
        seed()
        print("Isolated judge demo seeded. Start make judge-backend and make judge-frontend.")
    else:
        import uvicorn
        uvicorn.run("app.main:app", host="127.0.0.1", port=8110, reload=args.reload)


if __name__ == "__main__":
    main()
