# WorldLink Hotspot Cloud (WHC) — v0.3 Refined UI

**WORLDLINK SECURITY SYSTEMS** · Linking Security to Every Corner!

A Django multi-business starter platform for Wi-Fi hotspot operations, packaged for the Windows development workflow at `C:\Users\user\worldlink-projects\worldlink-hotspot-cloud`.

## What is in this ZIP

- **Mega Fish Point–inspired clean UI**: compact centered login, understated typography, consistent tables/cards/sidebar, phone-ready.
- **WorldLink platform logo upload** via `/admin/` → Cloud → Platform branding → Add: your uploaded logo displays on login and sidebar and becomes the browser favicon automatically.
- **Each business logo upload** via Business settings; displays in the company switcher/sidebar.
- One global CSS: `static/css/app.css`; one shared JS: `static/js/app.js`.
- Light and dark themes remembered by the browser.
- English and Kiswahili language switch on login, dashboard and public page (main UI translations; some admin/form validation text stays English).
- Business workspace isolation with roles: Owner / Manager / Cashier / Technician / Viewer.
- Router inventory with type, location, IP, model, serial and notes.
- Site/location management, Wi-Fi packages with time, price, speed, devices and optional data limit.
- Cryptographically random voucher batches (up to 500 per batch), CSV export.
- Manual cash/bank sale recording and reports, with duplicate-sale protection.
- Django Super Admin and security tests for cross-business access.
- Pillow image validation (PNG/JPG/WebP/GIF, max 2MB; SVG excluded). Uploaded files saved in `media/`; for production, serve only validated image MIME types safely.
- SQLite for local development; PostgreSQL environment option for later production hosting.

> **Important:** Routers are inventory records, **not connected**. Vouchers are database records, **not live Wi-Fi access codes**. Manual sale records are **not verified mobile-money transactions**. No RADIUS/Omada session management or mobile-money integration is implemented in this starter. Do not charge users for live internet access using this system yet.

## Run in Windows (first time)

1. Extract folder into `C:\Users\user\worldlink-projects\`.
2. Install **Python 3.11+** (check `python --version`). Internet is required for the first package installation.
3. Open `worldlink-hotspot-cloud` folder in VS Code.
4. Double-click `setup_windows.bat` or run from Command Prompt. It creates `.venv`, installs Django, generates a fresh local `.env`, migrates the database, then runs checks.
5. Double-click `create_admin.bat`. **Use your email address as the Username**. Enter a new strong password locally (never paste it into chat or Git).
6. Double-click `run_windows.bat`. Open **http://127.0.0.1:8000/**. Use `/login/` to log in; `/admin/` is WorldLink Platform Admin.
7. Admin first-time business setup: `/admin/` → **Companies** → Add company; then **Memberships** → Add your user to that company with `OWNER` role. Alternatively, while local development sign-up is enabled, visit `/register/` to create a separate business owner account automatically.
8. After signing in, add a **Location**, then a **Router**, then create a **Wi-Fi package**, then generate vouchers. This is inventory/workflow testing only.
9. Double-click `run_tests.bat` to run tenant-isolation, permissions and voucher tests.

### Manual terminal commands (PowerShell)

```powershell
cd C:\Users\user\worldlink-projects\worldlink-hotspot-cloud
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\init_env.py
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

The regular Windows `.bat` launchers work in CMD/double-click and do not require changing PowerShell execution policy.

## Source layout

```text
worldlink-hotspot-cloud/
  config/         Settings, URL router, WSGI/ASGI
  cloud/          Login, registration, dashboard, reports, translations & tests
  tenants/        Companies, memberships, roles & switching
  networks/       Locations, router inventory & package management
  vouchers/       Voucher batches, secure code generation & manual sales
  templates/      All HTML templates, reusable application shell
  static/css/     app.css (the ONLY CSS file)
  static/js/      app.js (the shared JavaScript)
  scripts/        Safe development .env generator
  setup_windows.bat, create_admin.bat, run_windows.bat, run_tests.bat
```

## English / Kiswahili

A single language switch sets `request.session['ui_lang']` to `en` or `sw`. The UI translation strings live in `cloud/templatetags/translations.py`, rendered through `{% load translations %}` and `{% t 'Some label' %}`. Add strings there when adding new pages; use one shared CSS and one shared JS throughout.

## Production checklist (NOT completed in this ZIP)

- Use HTTPS, PostgreSQL, Gunicorn, Nginx, restricted secrets, monitoring and secured backups.
- Change `.env`: `DJANGO_DEBUG=False`, `ALLOW_PUBLIC_SIGNUP=False`, a unique `DJANGO_SECRET_KEY`, proper `DJANGO_ALLOWED_HOSTS`, CSRF origins and secure proxy configuration. Consider separate app/DB credentials.
- Review Django admin staff permissions and customer onboarding before public signup.
- Add audit logs, email verification/2FA for sensitive users, billing enforcement and rate limiting before general public access.
- Implement and test **RADIUS/MikroTik AAA** and **Omada external portal integrations** with real network hardware. Only then allow active voucher codes and session state.
- Implement signed payment notifications, provider reconciliation, refunds/disputes and business merchant settlement with approved providers.
- Perform security, load, backup/recovery, privacy and regulatory checks before taking live customers.

## Sprint 2 recommended order

1. Real device adapters (MikroTik RADIUS first), hotspot authentication and session accounting.
2. Captive portal experience and voucher activation/expiry enforcement.
3. Business subscription billing, staff management & audit logging.
4. Live mobile-money payment integration and notifications through approved providers.
5. TP-Link Omada compatibility tests and managed network monitoring.

**Ownership:** This is a new original WorldLink prototype, not a copy of Scalynk source code or interface.

### Optional sample records for a realistic dashboard

If you want example plans, three clearly marked demo routers, and sample manual sales in your development database, run:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo --email your-email@example.com
```

Replace `your-email@example.com` with an **existing account's email-as-username**. Open **Switch business** to select the `DEMO • Kilimanjaro Guest Wi-Fi` workspace. This command is refused when `DJANGO_DEBUG=False` and never connects real routers or collects real money. It can be run once; it avoids adding duplicates.

## Upgrade existing v0.1 without losing data

1. Stop `runserver` (Ctrl+C), close VS Code, and copy this package over the **source folders**, keeping your existing `db.sqlite3`, `.env`, and `media/`. Do not extract into a nested second `worldlink-hotspot-cloud` folder.
2. New dependency: `Pillow` for uploaded logo validation.
3. Run:

```powershell
cd C:\Users\user\worldlink-projects\worldlink-hotspot-cloud
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver
```

4. At `http://127.0.0.1:8000/admin/`, open **Platform branding** and click Add; upload your actual WorldLink logo and Save. Only one platform record is allowed. Browser login and favicon now use that logo.
5. On the business dashboard open **Business settings** to upload that business's own logo.
6. Press Ctrl+F5 on the login and dashboard to refresh the CSS cache.

Only `static/css/app.css` contains our UI styling. Logo uploads are image files and do not create extra CSS.


## v0.3 — UI & expense update (2 Nov 2026)

- One unified `static/css/app.css` with navy / WorldLink blue / muted teal, DM Sans with system fallback.
- Route-aware Dashboard › Sales › Expenses breadcrumbs and animated expandable sidebar groups.
- Whole sidebar scrolls, scroll position survives navigation in same browser tab via `sessionStorage`; desktop hamburger collapses to icon rail; mobile hamburger opens a full drawer.
- Simplified light and dark interfaces, soft dropdown arrow animations on focus, compact action buttons.
- Editable/deletable routers, locations, packages (tenant-scoped, permission-checked, POST-only delete).
- Editable voucher batch names; deletion blocked for any batch with sold/voided codes. Do not edit printed voucher codes after selling.
- Expense tracking module with Add, Edit, Delete and summary, scoped to business; excludes live gateway payments.

### Upgrade an existing v0.2 installation

Unzip **over** the existing `worldlink-hotspot-cloud` source directory; never delete the current folder or the `db.sqlite3`, `.env`, or `media` directories. ZIP does not ship these files. From PowerShell in the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver
```

No production-grade hotspot authorization or mobile-money gateway is included; those require integration and independent security tests before hosting publicly.


### v0.4 UI refinements
Reworked auth branding/footer alignment, original-logo ring preloader, lighter focus styling, Chrome autofill neutralization, custom accessible EN/SW and business switch dropdowns, and desktop sidebar width 232px. No database changes or migrations.


## v0.5 — Connected users and WorldLink Control Center

**New pages**

- `/hotspots/sessions/`: business-only session history, expiry countdown, observed online count, package/router filters, CSV export.
- `/hotspots/customers/`: tenant-scoped Wi-Fi customers, add/edit/details, session history.
- `/console/`: WorldLink platform-wide overview (only a superuser or explicitly authorized WorldLink staff).
- `/console/businesses/`: all customer companies, account status, expiry, assigned users and statistics.
- `/console/users/`: all application login accounts (distinct from end-user Wi-Fi devices). Platform managers may enable/disable non-staff business users; staff/superuser changes remain in Django Admin.
- `/console/audit/`: platform account-status change history.

**Access model**

- Company owners/managers operate their own businesses; cashiers can register hotspot customers.
- Ordinary business owners **cannot** access `/console/` or browse other companies' sessions.
- A Django superuser can use `/console/` immediately, even without a business membership.
- To authorize a WorldLink employee without giving superuser access: in Django Admin, mark them **Staff**, then assign the **cloud → Platform branding → Can access WorldLink platform control center** permission. Add **Can change WorldLink business account status** only to trusted platform managers. Django Admin permissions remain separate.
- Platform staff do not implicitly obtain memberships in their customers' businesses.

**Online data accuracy**

No MikroTik RADIUS or Omada controller is connected yet. The app cannot magically discover live Wi-Fi clients. `HotspotSession` is a session record model and screens are integration-ready. Real online requires a trusted RADIUS/Omada adapter observation reported within 5 minutes, with an active status and unexpired session. `DEMO` and `IMPORT` source never count as online. Time-left counts down the stored expiry, not network access itself. There is intentionally no fake disconnect button.

`hotspots/services.py` exposes `record_authenticated_observation` for a future trusted controller adapter. **Do not expose this Python function directly as an unauthenticated HTTP endpoint.** Production integration will add device identity checks and the RADIUS/Omada accounting adapter. Payment APIs remain future work.

### Upgrade existing Windows installation (without resetting data)

Stop the existing runserver first. Download the v0.5 ZIP to Downloads and in PowerShell:

```powershell
cd C:\Users\user\worldlink-projects
$zip = "$env:USERPROFILE\Downloads\worldlink-hotspot-cloud-v0.5-ready.zip"
if (!(Test-Path $zip)) { throw "Download v0.5 ZIP first." }
Expand-Archive -LiteralPath $zip -DestinationPath . -Force
cd .\worldlink-hotspot-cloud
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver
```

The source ZIP does not contain `.env`, `db.sqlite3` or uploaded `media/` files; the upgrade should leave local data intact. **Still make your own backup before upgrading a production installation.**

### Optional clearly labeled sample records

Create a router and Wi-Fi package inside your business, then find its numeric company ID in Django Admin > Companies. Run:

```powershell
.\.venv\Scripts\python.exe manage.py seed_hotspot_demo --company-id 1 --confirm
```

Replace `1` with the actual ID. This creates 24 DEMO customer/session records by default (optional `--count 60`, maximum 250) and does not provide internet access or increase the online count. It is idempotent for a business with existing matching demo customers.


## v0.6 WorldLink operations console

WorldLink staff should visit **`/login/?portal=staff`**, then **`/console/`**.
The site now has a private Team directory, secure invitation-based staff onboarding,
business-owner invitations, business creation, platform branding, all-business
hotspot customer and session observation lists, and an audit trail.

Only the first Super Admin needs `python manage.py createsuperuser`. After that,
platform staff are invited from the Web UI; public registration cannot assign
staff roles. Keep invitation URLs private, and have each invited person set a
unique password. See `RELEASE_NOTES_v0.6.md` for detailed features and security
notes, including production requirements.


## EvPay payment gateway pilot (v0.8)

See [RELEASE_NOTES_v0.8.md](RELEASE_NOTES_v0.8.md) for sandbox credentials, webhook setup, launch/test commands and production safety requirements. This is a **single-business test lab**, not yet automated public Wi-Fi billing.
