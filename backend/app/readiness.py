"""Redacted setup report. Optional OAuth check never creates or captures an order."""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-paypal", action="store_true", help="Sandbox OAuth only; no transaction")
    args = parser.parse_args()
    from app.config import get_settings
    s = get_settings()
    report = {"environment": s.app_env, "paypal_environment": "sandbox_only",
              "paypal_credentials_configured": s.sandbox_configured,
              "webhook_configured": bool(s.paypal_webhook_id),
              "coach_sign_in_configured": bool(s.coach_password_hash),
              "simulation_enabled": s.simulator_available,
              "live_ai_enabled": s.enable_meta_api,
              "ai_key_configured": bool(s.model_api_key),
              "oauth_checked": False, "buyer_capture_verified": "requires recorded Sandbox buyer transaction",
              "webhook_delivery_verified": "requires observed verified provider event"}
    if args.check_paypal and s.sandbox_configured:
        from app.services.commerce.paypal import PayPal
        provider = PayPal(s)
        try:
            with provider._client() as client:
                provider._access_token(client)
            report.update(oauth_checked=True, oauth_ok=True)
        except Exception:
            report.update(oauth_checked=True, oauth_ok=False, oauth_error="Sandbox authentication/connectivity failed")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
