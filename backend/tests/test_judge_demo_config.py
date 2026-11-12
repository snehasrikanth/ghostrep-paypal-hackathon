"""Sandbox opt-in never enables inference or changes the isolated database/cookies."""
import os
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("sandbox", [False, True])
def test_judge_demo_credentials_require_explicit_opt_in(monkeypatch, sandbox):
    import app.config
    import app.judge_demo
    import uvicorn
    environment = dict(os.environ)
    monkeypatch.setattr(os, "environ", environment)
    monkeypatch.setattr("sys.argv", ["judge_demo"] + (["--sandbox"] if sandbox else []))
    monkeypatch.setattr(app.config, "Settings", lambda: SimpleNamespace(
        sandbox_configured=True, paypal_client_id="sandbox-client", paypal_client_secret="private-secret",
        paypal_merchant_id="merchant", paypal_webhook_id="webhook", coach_password_hash="private-hash"))
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: calls.append((a, kw)))
    app.judge_demo.main()
    assert environment["PAYPAL_CLIENT_ID"] == ("sandbox-client" if sandbox else "")
    assert environment["PAYPAL_CLIENT_SECRET"] == ("private-secret" if sandbox else "")
    assert environment["MODEL_API_KEY"] == ""
    assert environment["ENABLE_META_API"] == "false"
    assert environment["SESSION_COOKIE"] == "ghostrep_judge_athlete"
    assert "data-judge" in environment["DATABASE_URL"]
    assert calls[0][1]["port"] == 8110


def test_judge_demo_sandbox_refuses_missing_credentials(monkeypatch):
    import app.config
    import app.judge_demo
    monkeypatch.setattr("sys.argv", ["judge_demo", "--sandbox"])
    monkeypatch.setattr(app.config, "Settings", lambda: SimpleNamespace(sandbox_configured=False))
    with pytest.raises(SystemExit, match="credentials are missing"):
        app.judge_demo.main()
