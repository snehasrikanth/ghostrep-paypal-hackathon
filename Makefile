.PHONY: setup backend backend-dev frontend demo test check coach-password paypal-setup sandbox-status judge-setup judge-backend judge-frontend judge-sandbox-backend readiness webhook-gateway webhook-register

setup:
	@test -f .env || cp .env.example .env
	cd backend && uv sync --frozen --group dev
	cd frontend && npm ci

backend:
	cd backend && uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8100

backend-dev:
	cd backend && uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8100

frontend:
	cd frontend && npm run dev

demo:
	cd backend && uv run --frozen python -m app.commerce_demo

coach-password:
	cd backend && uv run --frozen python -m app.coach_password

# This gateway exposes only the callback, never the app or private coach routes.
webhook-gateway:
	cd backend && uv run --frozen uvicorn app.webhook_gateway:app --host 127.0.0.1 --port 8111 --no-access-log

webhook-register:
	@test -n "$(WEBHOOK_URL)" || (echo 'Set WEBHOOK_URL to the public HTTPS callback URL'; exit 1)
	cd backend && uv run --frozen python -m app.webhook_setup --url "$(WEBHOOK_URL)"

paypal-setup:
	cd backend && uv run --frozen python -m app.sandbox_setup

sandbox-status:
	cd backend && uv run --frozen python -m app.sandbox_setup --check

test:
	cd backend && uv run --frozen pytest
	cd frontend && npm test

check:
	cd frontend && npm run lint
	cd frontend && npx tsc --noEmit
	cd frontend && npm run build

# Isolated synthetic demo: separate data, ports, cookies and build output; no credentials used.
judge-setup:
	cd backend && uv run --frozen python -m app.judge_demo --seed

judge-backend:
	cd backend && uv run --frozen python -m app.judge_demo --reload

judge-frontend:
	cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8110 GHOSTREP_NEXT_DIST=.next-judge npm run dev -- --port 3110 --hostname 127.0.0.1

readiness:
	cd backend && uv run --frozen python -m app.readiness

# Opt in to Sandbox checkout on the isolated server; AI stays disabled.
judge-sandbox-backend:
	cd backend && uv run --frozen python -m app.judge_demo --sandbox --reload
