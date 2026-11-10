# WorldLink Hotspot Cloud — v0.7 Guest Portal + Payments Foundation

This source upgrade builds directly on v0.6.2, with the v0.6.1 staff-permission test fix included.

## What is working

- An optional public guest portal per business: `/wifi/<business-slug>/`.
- Business brand/logo favicon, customizable blue accent, English/Swahili, compact mobile layouts, and independent business packages.
- Public package selection and server-side pending payment requests with non-enumerable UUID receipt URLs.
- Business-specific **manual payment instructions** for M-Pesa, Airtel Money, Mixx by Yas, HaloPesa, bank, and cash. Every channel is manual; the presence of a channel does not imply an API integration.
- Pending/paid/cancelled order lifecycle, immutable package-price snapshot, unique order reference, merchant reconciliation reference, and audit records. Only owners and managers can confirm manually.
- Business dashboards for payment requests, payment methods, and public portal configuration.
- WorldLink staff read-only monitoring of payment requests from all registered businesses.
- One existing `static/css/app.css`, no new CSS system. Public page assets are local so a compatible router can whitelist the portal host.
- Automated unit tests for tenant isolation, disabled portals, order validation, receipt access, one-time payment confirmation, and WorldLink staff privileges.

## What is explicitly NOT connected yet

- No M-Pesa/Airtel/Mixx/Halo automatic collection API, STK/USSD prompt, payment verification webhooks, or automatic settlements.
- No MikroTik RADIUS or TP-Link Omada controller authentication; payment confirmation does NOT grant internet access.
- No voucher-to-router authorization, router disconnect, or bandwidth enforcement.
- No production-grade distributed anti-bot/rate-limit protection, SMS receipts, or live payment reconciliation.

## Windows upgrade from v0.6.2

Stop Django with Ctrl+C. **Back up** the entire local folder first, including `.env`, `db.sqlite3` and `media`.

```powershell
cd C:\Users\user\worldlink-projects
$zip = "$env:USERPROFILE\Downloads\worldlink-hotspot-cloud-v0.7-portal-payments-upgrade.zip"
if (!(Test-Path $zip)) { throw 'Download the v0.7 ZIP first' }
$project = 'C:\Users\user\worldlink-projects\worldlink-hotspot-cloud'
if (!(Test-Path "$project\manage.py")) { throw 'Project not found' }
$backup = "C:\Users\user\worldlink-projects\whc-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $project -Destination $backup -Recurse
Expand-Archive -LiteralPath $zip -DestinationPath 'C:\Users\user\worldlink-projects' -Force
cd $project
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test portal payments
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver
```

Open `/guest/settings/` to enable your portal; `/payments/methods/` to create manual payment methods; `/payments/` to see requests; `/console/payments/` for WorldLink staff; `/wifi/<business-slug>/` for the public portal.

### Local-only test content

With `DEBUG=True` in your local `.env`, optionally create three example packages and a test cash method:

```powershell
.\.venv\Scripts\python.exe manage.py seed_portal_demo --company-id 1 --confirm
```

Use the actual company ID from the WorldLink console, not necessarily `1`. This command refuses to run with `DEBUG=False`; it creates demonstration records only, not real transactions or internet access.

## Production readiness before real business deployment

1. Use PostgreSQL, enforce HTTPS, keep `DEBUG=False`, and configure secure cookies and backups.
2. Add distributed IP/phone request throttling and monitoring of fake orders and spam.
3. Agree on a licensed payment provider; integrate merchant onboarding and settlement ownership, secure secret management, verified signed webhooks, idempotency, and provider status polling. Never mark an order paid from a browser redirect.
4. Only after payment verification should the hotspot authenticator provision network access, with RADIUS/Omada accounting and accurate session expiry.
5. Build refund/dispute processes, financial audit/receipt rules, tax/compliance reviews, and PDPC protection requirements.
6. Validate captive-portal walled-garden and certificate access on real hardware (MikroTik/Omada) before customer pilots.

**Note:** Runtime Django tests require a Django installation. The archive was statically checked by the build tool; do not skip the local `manage.py` tests.
