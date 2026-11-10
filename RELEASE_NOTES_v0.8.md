# WorldLink Hotspot Cloud v0.8 — EvPay sandbox & USSD Test Lab

This release is a **controlled gateway integration pilot**. It does not activate routers, create vouchers, pay out money, or enable EvPay on public customer checkout. Existing manual payments still work as before.

## New functionality

* WorldLink business-owner/manager **EvPay test lab** at `/payments/evpay/` using the existing shared `static/css/app.css` and mobile layout.
* Authenticate to EvPay via `POST /api/auth/v1`, cache JWT on server with 30s renewal margin.
* Create signed and idempotent USSD collection request via `POST /api/v1/payment/ussd`. Store a separate test reference and status.
* Verify **signed** `payment.*` webhooks using HMAC-SHA256 over the **raw bytes**, strict 5-minute timestamp window and unique delivery ID.
* Compare webhook **reference, amount and currency** against original test. Never mark a payment from a browser redirect or unsigned callback.
* Reconcile by authenticated, signed `GET /api/v1/payment/{reference}`. Non-API demo data never counts as a real payment.
* Distinguish `PENDING`, `SUCCESS`, `SETTLED`, `FAILED`, `ON-HOLD`, `REFUNDED`, `REVERSED`, `UNKNOWN`. Prevent late callbacks from downgrading settled outcomes.
* Only one pilot company and one configured merchant account. **No shared platform wallet** for multiple independent businesses.

## Setup — credentials stay on your computer, NEVER paste them into ChatGPT

1. Create/get an approved EvPay **sandbox merchant** account and sandbox API credentials. Obtain the **correct sandbox API base URL directly from EvPay support or your dashboard**; don't use the live `https://api.evpay.co` host in sandbox mode.
2. Create a PUBLIC HTTPS webhook origin (e.g. a tunnel to your local server) to receive EvPay callbacks. `http://127.0.0.1:8000` is not reachable by EvPay.
3. Open `.env` (not `.env.example`) in the project folder. Append:

```ini
EVPAY_ENABLED=True
EVPAY_ENVIRONMENT=sandbox
EVPAY_PRODUCTION_CHARGES_ENABLED=False
EVPAY_COMPANY_ID=1
EVPAY_BASE_URL=https://YOUR-CONFIRMED-EVPAY-SANDBOX-API-HOST
EVPAY_PUBLIC_BASE_URL=https://YOUR-PUBLIC-HTTPS-HOST
EVPAY_CLIENT_ID=YOUR_SANDBOX_CLIENT_ID
EVPAY_CLIENT_SECRET=YOUR_SANDBOX_CLIENT_SECRET
EVPAY_SIG_KEY=YOUR_SANDBOX_API_SIGNING_KEY
EVPAY_WEBHOOK_SECRET=YOUR_SANDBOX_WEBHOOK_SIGNING_SECRET
EVPAY_WEBHOOK_TOKEN=YOUR_RANDOM_UNGUESSABLE_TOKEN
```

Replace `EVPAY_COMPANY_ID` with your **real WorldLink pilot business ID**. If EvPay specifies that the client secret is also the signing secret, use its exact instructions. The payment request signature may be the same secret as the webhook secret, but do not assume this without verification.

Generate webhook routing token safely in PowerShell:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(24))"
```

Paste the generated value only into `.env`. The secret itself must never be committed to GitHub. The callback address will be:

`https://YOUR-PUBLIC-HTTPS-HOST/payments/evpay/webhook/YOUR_RANDOM_UNGUESSABLE_TOKEN/`

Note: webhook **signatures**, not this URL token, are the payment authenticity check.

4. Migrate and run tests in your activated venv:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test payments.test_evpay payments.tests
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver
```

5. Visit `http://127.0.0.1:8000/payments/evpay/` while logged in as your WorldLink pilot business Owner/Manager. Test authentication **first**, then USSD.

### Sandbox test numbers (official EvPay test documentation)

* `255700000001` → simulated insufficient funds failure
* `255700000002` → simulated invalid PIN failure
* Any other valid `255[67]XXXXXXXX` number → simulated success

The sandbox intentionally **does not send a phone USSD prompt or move actual money**. It should send a signed webhook after a short delay. Use **Check status** if the webhook did not reach your development computer.

## Live pilot — not enabled by this release

Switching `EVPAY_ENVIRONMENT=live` alone is not enough: `EVPAY_PRODUCTION_CHARGES_ENABLED` remains `False` and the live call is blocked. Only after separate approval, signed webhook tests, HTTPS deployment and merchant settlement checks should you deliberately enable live charging and use confirmed live credentials. Live pilot requests have a basic 45-second duplicate-click guard (requires a shared Redis cache across multiple production workers) and are capped at TZS 1,000 per transaction and require an explicit authorized-payer checkbox. Never test a live debit on somebody else's phone without consent.

## Your checkout 403 (`Origin checking failed - null`)

The `Origin: null` request is blocked **correctly** by Django's CSRF defenses. Open the guest portal directly in a normal browser tab at `http://127.0.0.1:8000/` (not from a `file://` frame, sandboxed iframe, or privacy extension) and submit again. For a real HTTPS domain, configure the domain in `DJANGO_CSRF_TRUSTED_ORIGINS`; do **not** add `null` or disable CSRF on public checkout. The webhook endpoint alone is CSRF-exempt because it uses signed server-to-server authentication.

404 responses for Chrome DevTools discovery and an unconfigured `/service-worker.js` do **not** cause the payment problem.

## Scope limit

The current pilot uses ONE merchant account and ONE company ID. Do not make WorldLink the collector of other companies' funds without an approved merchant/settlement structure. Later we will add a per-business credential vault, distinct callback URL per merchant, operational reconciliation jobs, provider-specific controls and live customer checkout authorization.
