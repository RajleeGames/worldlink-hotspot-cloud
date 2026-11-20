# WorldLink EvPay + Omada EAP225 pilot — safe patch guide

This patch is based on GitHub `RajleeGames/worldlink-hotspot-cloud`, commit
`1ac7e86`. It **adds code and one additive payment migration**. It does **not**
contain `db.sqlite3`, media, `.env`, users, credentials, or existing data.

## What it does

- Public WorldLink captive portal → choose package → customer phone/operator →
  EvPay USSD push. Amount comes from the existing `WifiPlan`, not the browser.
- EvPay sends signed webhook to WorldLink VPS → success is assigned to exactly
  one hotspot business → shown on that business's dashboard and money page.
- A separate background worker authorizes that paid device through Omada
  External Portal API. **Unpaid, failed, or unknown payments never activate.**
- WorldLink staff verify actual merchant/bank settlement before a payment
  becomes withdrawable. Staff then handle verified-number withdrawals manually.
- Existing Omada voucher batches, manual sales, EvPay test lab, wallet database,
  user login, and GitHub history remain unchanged.

**Scope:** one EAP225, one approved business for initial real-money Wi-Fi
activation. The ledger/UI support separate companies, but additional companies
require independent controller configuration and written authorization to use
the shared WorldLink merchant account. Do not enable production by changing
the business ID list alone.

## 1. Windows / VS Code — apply without replacing your folder

In **PowerShell**, with the downloaded `worldlink_evpay_omada_PATCH.zip` on
your Desktop:

```powershell
cd "C:\Users\user\worldlink-projects\worldlink-hotspot-cloud"
git status --short
Expand-Archive -Path "$env:USERPROFILE\Desktop\worldlink_evpay_omada_PATCH.zip" -DestinationPath "$env:TEMP\worldlink-evpay-patch" -Force
git apply --check "$env:TEMP\worldlink-evpay-patch\worldlink_evpay_omada.patch"
git apply "$env:TEMP\worldlink-evpay-patch\worldlink_evpay_omada.patch"
git status --short
```

If **`git apply --check` fails, STOP**. Do not unzip over the main project or
reset the Git repo. Send its error output so the patch can be adjusted for your
specific version. Any unrelated existing work should stay in place.

Check everything against a **temporary test DB** (Django's test runner creates
its own test database, not your existing user database):

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test payments.test_live_collections
.\.venv\Scripts\python.exe manage.py migrate --plan
```

Before `migrate`, back up your **real** database while Django is stopped. If
you use the existing SQLite database, use SQLite's safe online-backup API:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; source=sqlite3.connect('db.sqlite3'); backup=sqlite3.connect('db.sqlite3.pre_evpay_backup'); source.backup(backup); backup.close(); source.close()"
.\.venv\Scripts\python.exe manage.py migrate
```

Check your existing owners/users can still log in. The migration adds the new
`EvPayCollection` and `EvPayCollectionDelivery` tables and **never deletes or
recreates your user tables**. If your DB is PostgreSQL, use a verified
`pg_dump` backup of the actual production database instead.

**Do not** run `flush`, `migrate ... zero`, `loaddata` from a blank install,
or create a new project folder in place of your current one.

## 2. VPS — test infrastructure first

No live USSD charges have been made by this patch. A local VS Code test cannot
reach EvPay with your VPS IP whitelist. On the VPS:

1. Confirm the **HTTPS** hostname/DNS and merchant API egress IP match EvPay's
   whitelist. Confirm with EvPay that WorldLink may collect for third-party
   hotspot businesses on its merchant account.
2. Set up a private VPN (e.g. WireGuard/Tailscale) from the VPS to your Windows
   Omada Controller PC. The controller was `192.168.1.49` on your shop LAN;
   that address is **not reachable from a public VPS without a VPN**. Keep the
   Windows Omada Controller running, or move it to always-on hosting.
3. Provision a controller HTTPS certificate trusted by the VPS and named for
   the VPN hostname/IP, then verify connection from the VPS. Do **not** expose
   TCP 8043 to the public Internet or disable TLS checks.
4. Create a dedicated **Hotspot Operator** under the Omada Controller (not a
   controller administrator). Record the controller ID from its URL.
5. Keep your working voucher SSID unchanged. For a safe pilot create a separate
   SSID such as `WORLDLINK-PAY` on the EAP225. For this SSID select Omada
   **Hotspot → Portal → External Portal Server**, pointing to
   `https://YOUR-PUBLIC-DOMAIN/wifi/YOUR-COMPANY-SLUG/`.
6. Allow that domain and required DNS/portal access in the captive portal's
   pre-authentication access rules (walled garden). Confirm a fresh phone on
   the pilot SSID sees the WorldLink package page **without internet**.
7. Install a secured shared Redis on the VPS for anti-spam and idempotency
   throttles. Never expose its port publicly. Run `pip install -r requirements.txt`
   in the existing VPS venv after reviewing pinned dependencies.

Set **real secrets only in the VPS `.env`** (never GitHub):

```dotenv
EVPAY_ENABLED=True
EVPAY_ENVIRONMENT=live
EVPAY_PRODUCTION_CHARGES_ENABLED=True
EVPAY_PUBLIC_CHECKOUT_ENABLED=True
EVPAY_COMPANY_ID=YOUR_APPROVED_COMPANY_PK
EVPAY_COLLECTION_COMPANY_IDS=YOUR_APPROVED_COMPANY_PK
EVPAY_PUBLIC_MAX_AMOUNT_TZS=1000
EVPAY_BASE_URL=https://EVPAY-APPROVED-PRODUCTION-API-ORIGIN
EVPAY_PUBLIC_BASE_URL=https://YOUR-PUBLIC-DOMAIN
EVPAY_CLIENT_ID=YOUR_PRIVATE_VALUE
EVPAY_CLIENT_SECRET=YOUR_PRIVATE_VALUE
EVPAY_SIG_KEY=YOUR_PRIVATE_VALUE
EVPAY_WEBHOOK_SECRET=YOUR_PRIVATE_VALUE
EVPAY_WEBHOOK_TOKEN=YOUR_EXISTING_TEST_LAB_ROUTE_TOKEN
EVPAY_COLLECTION_WEBHOOK_TOKEN=NEW_LONG_RANDOM_SECRET_ROUTE_TOKEN
WHC_REDIS_URL=redis://127.0.0.1:6379/1

OMADA_LIVE_ENABLED=True
OMADA_PILOT_COMPANY_ID=YOUR_APPROVED_COMPANY_PK
OMADA_CONTROLLER_URL=https://YOUR-PRIVATE-VPN-OMADA-HOST:8043
OMADA_CONTROLLER_ID=YOUR_CONTROLLER_ID_FROM_OMADA_URL
OMADA_OPERATOR_NAME=YOUR_DEDICATED_OPERATOR
OMADA_OPERATOR_PASSWORD=YOUR_PRIVATE_VALUE
OMADA_CA_FILE=/etc/worldlink/omada-controller-ca.pem
OMADA_AP_MAC=B8-FB-B3-79-B5-60
OMADA_SSID=WORLDLINK-PAY
```

EvPay's webhook URL for **customer purchases** is:

`https://YOUR-PUBLIC-DOMAIN/payments/evpay/collections/webhook/NEW_LONG_RANDOM_SECRET_ROUTE_TOKEN/`

Ensure the merchant settings really deliver events to this callback URL.
Webhook signatures are mandatory. Do not use the separate EvPay test-lab
webhook to activate customers. EvPay's published webhook documentation says
the webhook HMAC uses the merchant's API signing secret (also called the client
secret); configure the **actual secret confirmed in your EvPay account**, not
a newly invented one.

You can find your business PK safely:

```bash
python manage.py shell -c "from tenants.models import Company; print(list(Company.objects.values_list('id','name','slug')))"
```

## 3. Safely deploy the commit to VPS

Once the patched Windows Git repo is tested and committed/pushed normally,
on the VPS use `git pull --ff-only` in its **existing** checkout; review
`git status` first. Back up the **actual** production DB before applying migrations.
For SQLite (when the application is stopped):

```bash
python -c "import sqlite3; source=sqlite3.connect('db.sqlite3'); backup=sqlite3.connect('db.sqlite3.pre_evpay_backup'); source.backup(backup); backup.close(); source.close()"
python manage.py check --deploy
python manage.py migrate --plan
python manage.py migrate
```

Restart only your known WorldLink web service (service name varies by VPS),
then start the background activation worker under `systemd`, for example:

```bash
cd /path/to/existing/worldlink-hotspot-cloud
.venv/bin/python manage.py activate_evpay_omada --loop --interval 5
```

Use a supervised `systemd` service with automatic restart for production;
do not rely on a Windows laptop VS Code terminal to run the VPS worker.
Also schedule a safe **read-only** missing-webhook backstop every 5 minutes:

```bash
.venv/bin/python manage.py reconcile_evpay_collections --limit 25
```

This only queries original EvPay references; it **never sends another USSD
push**. Any newly verified payment is picked up by the Omada worker.

## 4. Run one inexpensive, real end-to-end pilot

1. Confirm Omada `Devices` shows EAP225 **Connected**. Choose the pilot SSID
   and check the phone has **no Internet** before paying.
2. Open the captive portal through Omada's **automatic redirect** (do not
   manually browse to the public URL, which lacks device context).
3. Buy a TZS 100–1,000 test plan. Approve only the phone's official mobile
   money USSD prompt; never type a PIN in the web form.
4. EvPay callback must mark the unique purchase **SUCCESS/SETTLED**. Confirm
   exactly the correct business dashboard shows its amount. Other businesses
   must not see the purchase.
5. The background worker should authorize the **same device** through Omada;
   verify the guest obtains Internet and access stops after the plan's period.
6. WorldLink staff compare EvPay's statement/bank settlement, then use the
   `wallet/worldlink/` **EvPay collections awaiting bank clearance** list to
   record actual settlement. Only then can the owner request a withdrawal using
   a previously WorldLink-verified destination.
7. WorldLink **manually** sends the money, records the real transfer ID, and
   marks the withdrawal paid. No automatic EvPay payout is used.

If the gateway is uncertain, the application records `UNKNOWN` and **will
not** send an automatic repeat charge. Reconcile the original reference via
the owner payment list before asking anyone to pay again.

## Known pilot limitations — do not label this production-ready yet

- EvPay's merchant contract/authorization for pooled submerchant collections
  must be confirmed, as must relevant Tanzanian payment-service obligations.
- Multiple independent business controllers are **not configured** by this
  one-EAP pilot. One controller and one pilot business may be activated.
- Confirm real callback event schema and Omada 6.3 behavior from the first
  supervised transaction. Tests use mocks because the VPS is IP-whitelisted.
- Reversals after a paid Wi-Fi activation need an operations process to remove
  access/reconcile any credited ledger balance before full production rollout.
- Displayed EvPay earnings are **gross** TZS. Agree how EvPay fees, taxes,
  commissions and chargebacks affect the owner's eventual net withdrawal before
  onboarding additional businesses.
- Keep reliable backups, firewall/VPN, Redis, webhook secrets, systemd worker,
  TLS, and restricted WorldLink finance accounts in place.

**Rollback:** set `EVPAY_PUBLIC_CHECKOUT_ENABLED=False` and
`OMADA_LIVE_ENABLED=False` on the VPS, restart services and keep the database
and payment records intact. Do **not** reverse migrations or delete customer
payment records. Review any pending money/withdrawal items manually.
