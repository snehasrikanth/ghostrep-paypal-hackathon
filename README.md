# GhostRep

AI-assisted training, rep-linked movement feedback, and optional coaching through PayPal.

An athlete can build a training week, record a barbell squat, inspect feedback against their own reference, and choose paid expert support. Generated plans can go directly to a live-coach review request without recording a set. The athlete approves the shared context and fixed price; the server verifies PayPal capture before releasing the service.

## Run locally

Requirements: Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js 24 LTS with npm, and FFmpeg/FFprobe on PATH. Initial dependency installation and the first pose-model download require network access.

```sh
make setup
```

Start these in separate terminals:

```sh
make backend-dev
```

```sh
make frontend
```

Open **http://localhost:3100**. The API runs at **http://127.0.0.1:8100**; `/health` reports enabled providers. `make setup` creates `.env` from `.env.example` only when it is missing. Keep private credentials in `.env`.

## Explore without credentials or paid inference

Use the isolated example environment:

```sh
make judge-setup
```

Then run these in separate terminals:

```sh
make judge-backend
```

```sh
make judge-frontend
```

Open **http://localhost:3110/demo**, then **Explore the example workspace**. Choose a plan review or a sample movement recording. Example purchases use simulated payments; the example coach can review these requests through `/coach`. No real appointment is reserved. Choose **Back to my account** to restore the preceding athlete identity.

This environment has separate data, cookies and build output. It disables paid model calls and merchant credentials by default. Do not reset an existing database to rehearse a recording.

## Product walkthrough

1. **Profile and plan:** select goals, equipment, schedule and restrictions. Review the proposed week before activating it.
2. **Record and analyze:** barbell squat supports pose-based, rep-by-rep analysis. Other exercises support logging and video replay. Every eligible workout includes barbell squat; saved equipment, restrictions, exclusions and unfamiliarity take priority.
3. **Ask the AI coach:** replay a supporting rep and ask questions about saved evidence. Source labels distinguish measurements, deterministic summaries and live-model interpretation.
4. **Choose support:** the commerce agent uses reliable saved evidence, a fixed catalog and an optional budget. Recommendations do not create purchases automatically.
5. **Review a plan with a coach:** use **Ask a live coach**, select matching preferences and request a session time. Sharing consent and purchase approval are separate.
6. **Pay and track:** PayPal buyer approval is followed by server verification of capture identity, merchant, amount and currency. Pending payment keeps fulfillment locked. Appointment requests, confirmations, feedback and refunds have separate states on the receipt.
7. **Coach workflow:** a separate authenticated workspace exposes only consented context. A coach confirms availability and supplies a private meeting link. Draft feedback requires explicit approval before delivery.

The fixed commerce catalog is AI Technique Review **$4.99**, Expert Video Review **$14.99**, and Personal Coaching Session **$29.99 / 30 minutes**, each a one-time purchase. Historical instructor orders retain their purchased terms.

## PayPal test checkout and coach sign-in

The integration is pinned to PayPal Sandbox. It does not support real-money payments.

1. Create a Sandbox REST application under your **Business seller** account in the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/applications/sandbox).
2. Run `make paypal-setup` in an interactive terminal. Enter `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and the same seller's `PAYPAL_MERCHANT_ID` using hidden prompts. An optional `PAYPAL_WEBHOOK_ID` can be added after registering HTTPS.
3. The setup prompts for a private coach password when no hash exists. Alternatively run `make coach-password`. Neither command prints the password. The normal coach workspace is `/coach`; the sample-coach shortcut cannot access actual Sandbox tasks.
4. Restart the API after changing private configuration.
5. Use an owned plan or recording for PayPal checkout. Use a **Personal Sandbox buyer account**, separate from the Business seller. Get its test email and password under [Sandbox Accounts](https://developer.paypal.com/dashboard/accounts). Do not use the merchant client secret as a buyer password.
6. After buyer approval, inspect the receipt. Only a completed capture enables fulfillment. `PENDING_REVIEW` is provider review, not successful settlement. Do not charge again to recover an uncertain response.

For actual Sandbox checkout in the isolated app, replace `make judge-backend` with:

```sh
make judge-sandbox-backend
```

This retains the isolated database and keeps paid AI disabled, while allowing owned non-sample purchases to use the configured Sandbox merchant. Synthetic example purchases remain simulated. `make sandbox-status` and `make readiness` print redacted configuration status.

### HTTPS webhooks

Register `/reviews/paypal/webhook` on the **same Sandbox REST application**. Localhost cannot receive provider notifications without an HTTPS reverse proxy or tunnel.

For the isolated API on port 8110, `make webhook-gateway` starts a loopback listener on 8111 that forwards only signed callback POSTs. It exposes no athlete, coach, profile, or media routes. Forward a public HTTPS tunnel to that gateway, then register its full callback URL:

```sh
make webhook-register WEBHOOK_URL=https://YOUR-HOST/reviews/paypal/webhook
```

Restart the isolated backend after registration so it reads the saved ID. Registration subscribes to supported order-approved/completed, capture-completed/pending/denied/refunded and refund-pending/failed events. The backend verifies signatures with PayPal, retrieves authoritative resources, checks purchase identity and amount, and deduplicates accepted events. Pending capture IDs are retained without releasing fulfillment.

A temporary tunnel must remain running and its URL can change on restart. Configured subscriptions do not prove observed delivery: verify an authentic provider event and the resulting receipt. Simulator notifications are not a substitute for authentic signature verification.

## AI configuration

The default configuration uses a deterministic planner and saved-evidence summaries, with paid external inference disabled. Actual video pose extraction uses MediaPipe; its model downloads automatically on first use. Live model capabilities are optional:

- Set `MODEL_API_KEY`, `ENABLE_META_API=true`, and the appropriate `WORKOUT_PROVIDER` / `COACHING_PROVIDER` to `meta_live`.
- Optional segmentation uses `SEGMENTATION_PROVIDER=meta_live`; it is independent of planning and coaching.
- Live calls require explicit approval and the applicable athlete consent. A configured key alone does not start a call; local failures never silently fall through to paid inference.

Exact models, optional call/spend controls and timeouts are in `.env.example`. Commerce matching itself is deterministic; it does not invent prices or authorize transactions.

## Build and verify

```sh
make test
make check
```

`make test` runs offline backend and frontend regressions, including purchase ownership, tampering, pending capture, webhook replay, refunds, scheduling, coach access and plan constraints. Optional tests requiring private media skip when those files are absent.

For a production frontend:

```sh
cd frontend
npm run build
npm start
```

The production build uses Webpack with the Tailwind PostCSS plugin. Tests, lockfiles, fonts' license notices and required fixtures are retained in the source package. Generated files, local environments, dependencies, databases, recordings and cached models are excluded.

## Implementation and limits

FastAPI, SQLAlchemy and SQLite provide the backend. Next.js and React provide the frontend. MediaPipe, OpenCV and optional external models provide movement processing. PayPal Orders v2, JavaScript SDK v6, capture/refund APIs and verified webhooks provide commerce. Staff sessions are distinct from athlete sessions; private access is not granted by an athlete cookie.

Training, pose processing and replay foundations predate the PayPal edition. This edition adds the consented commerce agent, fixed catalog, PayPal transaction controls, plan-to-coach handoff, preference snapshots and coach fulfillment workflow.

Coach matching is a request workflow, not a connected directory with guaranteed real-time availability. A requested appointment is not a confirmed session, and confirmed time is not proof a call occurred. Measurement differences are not technique grades, diagnoses or proof of improvement. The local SQLite/job architecture and anonymous athlete cookie are intended for evaluation; durable account recovery and production staffing are not implemented.

## Source export and license

```sh
python3 scripts/package_submission.py --output dist/GhostRep-submission.zip --directory dist/GhostRep-submission
```

The exporter creates a clean source directory and ZIP from an explicit allowlist, rejects symlinks and detected private credentials, and excludes development notes and generated artifacts. It does not publish anything. Do not add merchant secrets or private coach credentials to a public repository; provide required test access through the submission's supported private mechanism.

Source code is licensed under [MIT](LICENSE). Preserve [third-party notices](THIRD_PARTY_NOTICES.md) and `docs/licenses/` when distributing the application.
