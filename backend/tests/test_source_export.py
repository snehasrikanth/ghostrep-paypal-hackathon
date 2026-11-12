import importlib.util
from pathlib import Path


def exporter():
    path = Path(__file__).resolve().parents[2] / "scripts/package_submission.py"
    spec = importlib.util.spec_from_file_location("ghostrep_source_export", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_excludes_private_state_and_internal_documents():
    module = exporter()
    for name in (".env", ".env.coach-access", "PROGRESS.md", "docs/DEMO_SCRIPT.md", "docs/private/WEBHOOK_RUNTIME.md",
                 "backend/data-judge/athlete.db", "backend/app/__pycache__/private.py", "backend/app/../../private.py",
                 "frontend/node_modules/private.ts", "/backend/app/main.py", "dist/GhostRep-PayPal-Submission.mp4"):
        assert not module.public_file(name), name
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "frontend/postcss.config.mjs",
                 "backend/app/main.py", "frontend/public/demos/squat-example.mp4", "docs/licenses/sora-OFL.txt"):
        assert module.public_file(name), name


def test_secret_scan_includes_hashes_and_private_coach_login_file(tmp_path):
    module = exporter()
    module.ROOT = tmp_path
    (tmp_path / ".env").write_text("PAYPAL_CLIENT_SECRET='private-merchant-secret'\nCOACH_PASSWORD_HASH='private-coach-password-hash'\n")
    (tmp_path / ".env.coach-access").write_text("Coach password: private-local-coach-password\n")
    (tmp_path / ".env.example").write_text("MODEL_API_KEY=public-placeholder-value\n")
    values = module.local_keys()
    assert b"private-merchant-secret" in values
    assert b"private-coach-password-hash" in values
    assert b"private-local-coach-password" in values
    assert b"public-placeholder-value" not in values
