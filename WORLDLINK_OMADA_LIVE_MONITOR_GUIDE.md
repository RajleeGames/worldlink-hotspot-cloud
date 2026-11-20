# WorldLink Omada read-only monitor — approved pilot

This is an **incremental** patch on top of router onboarding v1 + the same-origin CSRF fix. It adds a separate last-observed AP status record (`networks.0004_omada_device_observation`). It does **not** change the tested EvPay USSD charge, webhook, Omada Hotspot Operator authorization, payment accounting, or withdrawal logic. It does not enable a second company or universal router support.

## What the status actually means

- `Connected`: an authenticated Omada Open API read returned an explicitly recognized **connected** state for the approved AP MAC in the selected site within the last 120 seconds.
- `Offline`: Open API explicitly reported disconnected/isolated/heartbeat missed.
- `AP not found`: the authorized site list completed successfully but the approved AP MAC was absent.
- `Status not recognized`: a controller version returned an unfamiliar status representation (including **undocumented numeric codes**). We don't assume these mean online.
- `Controller unavailable`: authentication, TLS, API, or parsing failed.
- `Not recently verified`: no reading, an expired reading, or a router that no longer exactly matches the staff-reviewed pilot configuration.

The read-only monitor checks the **single WorldLink-approved Eaglelink pilot** only. Each business's router records are isolated in the dashboard. Saving an AP MAC/Controller ID or marking a form "reviewed" does **not** grant public payment or internet activation for other businesses.

## Windows: apply, test, and push

Download `worldlink_omada_live_monitor_PATCH.patch` to Downloads. From the repository in VS Code PowerShell:

```powershell
cd C:\Users\user\worldlink-projects\worldlink-hotspot-cloud
git status --short
git apply --check "$env:USERPROFILE\Downloads\worldlink_omada_live_monitor_PATCH.patch"
git apply "$env:USERPROFILE\Downloads\worldlink_omada_live_monitor_PATCH.patch"
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test networks.tests networks.test_omada_monitor
git diff --check
git status --short
git add .env.example config/settings.py cloud/context_processors.py cloud/views.py
git add networks/models.py networks/views.py networks/omada_monitor.py networks/test_omada_monitor.py
git add networks/migrations/0004_omada_device_observation.py networks/management/
git add templates/base.html templates/cloud/dashboard.html templates/networks/routers.html
git add deploy/worldlink-omada-monitor.service.example WORLDLINK_OMADA_LIVE_MONITOR_GUIDE.md
git commit -m "Monitor approved Omada pilot AP status via read-only Open API"
git push origin master
```

## VPS: configure credentials privately

**Do not paste credentials in chat, terminal screenshots, or GitHub.** The existing Omada **Hotspot Operator** account continues handling paid access; this new credential needs **read-only** site/device permissions only. Create a separate Open API credential in Omada **Global View → Settings → Platform Integration → Open API**, scoped to your approved pilot site.

Edit `/var/www/worldlink-hotspot-cloud/.env` **on the VPS** (never commit it):

```dotenv
# Choose ONE mode. Client mode works on older v6 controllers too.
OMADA_OPENAPI_CLIENT_ID=<paste locally into your VPS .env>
OMADA_OPENAPI_CLIENT_SECRET=<paste locally into your VPS .env>
OMADA_OPENAPI_API_KEY=

# OR, only if your Omada version supports an API Key credential:
# OMADA_OPENAPI_CLIENT_ID=
# OMADA_OPENAPI_CLIENT_SECRET=
# OMADA_OPENAPI_API_KEY=<paste a VIEW-only key locally>

# Leave blank if the credential sees exactly one site.
# If it sees multiple, set the intended approved pilot Site ID.
OMADA_OPENAPI_SITE_ID=
```

For an API Key, don't leave any Client credentials set; for a Client credential, leave `OMADA_OPENAPI_API_KEY=` empty. Keep the existing `OMADA_CONTROLLER_URL`, `OMADA_CONTROLLER_ID`, `OMADA_AP_MAC`, `OMADA_SSID`, `OMADA_LIVE_ENABLED`, and existing payment variables unchanged.

## VPS: deploy and verify without a charge

Back up the SQLite database **before** running migrations, as you did for the previous release. Then run:

```bash
cd /var/www/worldlink-hotspot-cloud
source .venv/bin/activate
git status --short
git pull --ff-only
python manage.py check
python manage.py migrate --plan
python manage.py migrate
sudo systemctl restart worldlink-hotspot.service
sudo systemctl is-active worldlink-hotspot.service
python manage.py poll_omada_pilot
```

The last command performs at most one authentication request and bounded **GET-only** site/device reads. It doesn't send a payment or change AP settings. If it prints an error, **stop here** and resolve the error; don't install a repeating service until a manual probe succeeds.

If the result is `Status not recognized`, use the following **safe** command to show only the normalized AP status code (no API tokens):

```bash
python manage.py shell -c "from networks.models import OmadaDeviceObservation as O; o=O.objects.order_by('-checked_at').first(); print('STATUS:',o.state if o else 'NONE'); print('API STATUS FIELD:',o.reported_status if o else 'NONE')"
```

When the one-time check works, enable background monitoring every 30 seconds:

```bash
sudo cp deploy/worldlink-omada-monitor.service.example /etc/systemd/system/worldlink-omada-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now worldlink-omada-monitor.service
sudo systemctl is-active worldlink-omada-monitor.service
sudo journalctl -u worldlink-omada-monitor.service --since "2 minutes ago" --no-pager
```

If the VPS systemd service runs under a different Unix user than `miraji`, edit its `User=`/`Group=` lines first. Keep `worldlink-hotspot.service`, `worldlink-evpay-fast.service`, and `worldlink-evpay-omada.service` unchanged.

In the web dashboard open **Eaglelink → Dashboard → Omada AP status** and **Network → Routers**. With a successful recent check the EAP225 will display its actual controller-reported state; it is **not** inferred from a submitted setup form. Wait up to 30 seconds after enabling the service, then refresh.

## Important before wide launch

- Omada v6 controller API paths/status formats vary; check **Online API Document** in the actual Omada controller for version details. An unrecognized numeric status is deliberately displayed as unknown until verified.
- The existing single-company payment/activation pilot stays unchanged. A different customer with another router needs a separately approved secure connector, tenant-scoped credentials, and tested device-specific activation. Do not reuse Eaglelink's shared controller/API credentials across unrelated businesses.
- Controller machine and Tailscale Serve must remain online for status checks **and** paid activation. The VPS-to-PC HTTPS certificate must remain trusted; no TLS bypass or public port 8043.
- Production credentials were previously disclosed in screenshots/chat. Coordinate rotating the Django, EvPay and Omada secrets before broad public enrollment; rotate both ends of each integration together to avoid interrupting payments.
