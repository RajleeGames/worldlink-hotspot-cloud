# WorldLink Hotspot Cloud · Owner Wallet & Manual Withdrawals (v0.9)

This upgrade adds a simple business money screen and a WorldLink finance work queue to the existing Django project.

## What an owner sees

- **Money & withdrawals** in the business sidebar and a link from the dashboard.
- Available balance, total cleared collections, amounts reserved for requested withdrawals, and total paid manually.
- Receiving numbers with provider, registered account name and verification status.
- A password-confirmed request form using *only* WorldLink-verified numbers.
- A request list with pending, processing, paid, rejected and cancelled statuses.

## What WorldLink staff sees

- A **Withdrawals & collections** work queue in the Control Center, with open-request counts.
- Pending receiving numbers with **approve/reject** controls and mandatory independent evidence notes.
- A manual withdrawal review: **claim** the request first (blocks owner cancellation), **send payment using an external MNO/bank channel**, verify successful transfer, and **mark paid** with a real transaction reference. Or reject and release the reserved balance.
- Finance managers can register real, cleared collections against a unique provider payment reference and independent bank/merchant statement reference. Changes are audited.
- View-only support staff can see the queue but cannot verify numbers, credit wallets or mark payments.

## Critical accounting and security rules

1. **No payout API exists in this release.** No code sends mobile money; manual payment is required.
2. **No automatic public-checkout credits yet.** The existing EvPay module is an *isolated payment test lab* and the public portal supports manual payment instructions. Until approved production checkout is connected, funds appear only after a finance manager records a real, independently reconciled, cleared collection. The integration service is wallets.services.record_settled_collection. It must not be called from the pilot/test flow.
3. A phone number's syntax is validated, but this **does not prove number ownership or account name**. WorldLink must check the real name and number against an authorized MNO/provider source before pressing Verify. No automated telecom identity lookup is present.
4. Customer's manual voucher/cash sales and sandbox payments **never increase** the WorldLink-held wallet.
5. A withdrawal request immediately reserves the amount. Conditional SQL updates block overdraw; every status change and credit has an audit record.
6. Owners confirm their login password when adding a receiving number or requesting a withdrawal. Requests use a one-time form nonce to prevent accidental duplicate submits. Sensitive staff actions are POST+CSRF-only.
7. Existing database records are preserved by additive migrations. There is no migration that deletes or rewrites existing payments.
8. **Before operating at financial scale**, obtain legal/provider confirmation of the funds-holding arrangement, implement production collection callbacks and reconciliation, secure step-up MFA for high-risk actions, set payout minimum/fees and limits, introduce independent approval for large payouts, and migrate SQLite to PostgreSQL for stronger concurrent-transaction behavior.

## Local test (Windows PowerShell)

From the extracted project folder:

~~~powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test wallets
.\.venv\Scripts\python.exe manage.py runserver
~~~

Existing project environment variables are still required when running with production settings. **Do not copy a demo database or .env over a live installation.**

## Safe VPS deployment

Use the ZIP as a **source release**, not as a database backup. Check differences against your current VPS checkout before copying.

1. Back up the live database using its native backup mechanism. Back up the application files and environment file.
2. Inspect this release in a separate folder. Use rsync --dry-run to review proposed changes to the project, excluding .env, .venv, the database, uploads, and Git metadata.
3. Deploy only the approved changed source/migration files (or commit them and git pull with your normal workflow). Never replace a running database with a ZIP copy.
4. In /var/www/worldlink-hotspot-cloud, run:

~~~bash
.venv/bin/python manage.py migrate --plan
.venv/bin/python manage.py migrate
.venv/bin/python manage.py check
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart worldlink-hotspot.service
~~~

Confirm your actual service name from systemctl before restarting; the supplied service file is only a reference. If a migration or verification fails, stop and investigate before exposing the withdrawal feature to owners.

## URLs

- Business owner: /wallet/
- WorldLink staff: /wallet/worldlink/
- Real cleared collection entry: /wallet/worldlink/collections/new/

No outgoing SMS is sent for withdrawal requests. The request is stored server-side and appears instantly in the WorldLink Control Center queue. Add official SMS/email alerts later if required.
