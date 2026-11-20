# WorldLink central Omada — customer onboarding v2

## What this release actually enables

- Any signed-up business can add a TP-Link Omada router and request **WorldLink central Omada** connection without Tailscale, a controller password, or a self-hosted controller.
- WorldLink platform staff review each application and **manually create/assign a site in the central TP-Link Omada controller**. Site IDs are never supplied or approved by the customer.
- The customer sees the assigned device Inform URL and follows AP setup steps. Staff adopts the AP in Omada; an independent read-only Open API monitor verifies the physical AP online/offline status for its own site.
- The customer's dashboard and router list show only that customer's AP and **fresh** observed states (two-minute expiry). An old observation cannot show as current.
- Existing Eaglelink single-company live payment and activation services are **not modified**. A newly connected business does **not** automatically gain access to WorldLink's EvPay merchant. That is a separate per-tenant payment/settlement/authorization launch phase.

## Deploy to the existing Django VPS

The initial development changes should be pushed to GitHub from the developer's local checkout before these steps. Do not commit `.env` or passwords.

```bash
cd /var/www/worldlink-hotspot-cloud
source .venv/bin/activate
git status --short
git pull --ff-only
python manage.py check
python manage.py migrate --plan
```

Take your normal database backup before applying `networks.0005_omada_central_sites`, then:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart worldlink-hotspot.service
sudo systemctl is-active worldlink-hotspot.service
```

Do not blindly overwrite any VPS-local changes or disable CSRF. If `git status --short` shows local edits, preserve and inspect them before pulling.

In `/var/www/worldlink-hotspot-cloud/.env` add:

```dotenv
OMADA_CENTRAL_INFORM_HOST=omada.worldlinksecurity.co.tz
```

The existing variables `OMADA_CONTROLLER_URL=https://omada.worldlinksecurity.co.tz` and `OMADA_CONTROLLER_ID=<WorldLink-controller-API-ID>` must continue to identify the **central** controller. The API ID, site Inform URL `omadacId`, and Open API `siteId` are **different identifiers**; never paste one into the other's place.

For automatic status verification, create a **view-only** Open API application in **central Omada > Global View > Settings > Platform Integration > Open API**, authorized to see all relevant customer sites. Configure the existing `OMADA_OPENAPI_CLIENT_ID` and `OMADA_OPENAPI_CLIENT_SECRET` (or view-only API key) on the Django VPS, not in the customer's form. No password or API key belongs in the browser.

Once `.env` is saved, verify the site listing:

```bash
python manage.py list_omada_sites
```

It should list entries like `Customer Site: <actual-Open-API-siteId>`. If it fails, fix controller connectivity, API permissions and the certificate before accepting new APs.

Start read-only monitoring with a minute-level cron job on the **Django VPS**. Use your own current crontab without deleting existing entries:

```cron
* * * * * cd /var/www/worldlink-hotspot-cloud && /usr/bin/flock -n /tmp/worldlink-omada-managed.lock /var/www/worldlink-hotspot-cloud/.venv/bin/python manage.py poll_omada_managed --limit 50 >> /tmp/worldlink-omada-managed.log 2>&1
```

Run once manually first:

```bash
python manage.py poll_omada_managed --limit 50
```

If there are no approved central APs yet, it correctly reports zero. When the controller cannot be reached, status becomes unavailable — never falsely green.

## Test with one new business (no payment)

1. On `https://wifi.worldlinksecurity.co.tz/`, the business owner creates an account, goes to **Network > Routers > Add router**, selects **TP-Link Omada**, and enters a name, model, serial and location. A default "Main site" is created if none exists.
2. The business owner is redirected to **Omada setup**, leaves **WorldLink central Omada (recommended)** selected, enters the **real AP MAC** from the sticker and intended **guest SSID**, and clicks **Request WorldLink review**. No VPN, Tailscale, passwords, Open API credentials, or controller IDs are requested.
3. A WorldLink team member opens **Control Center > Omada router requests**. For this customer, manually create an independent site in the central Omada UI. Obtain the **exact site's** device Inform URL (`omadacId`, copy the hexadecimal value) and `siteId` from `python manage.py list_omada_sites` on the Django VPS. Verify both correspond to the same business site. In the WorldLink review form enter the site name, Inform `omadacId`, Open API `siteId`, then click **Approve site details**.
4. The customer refreshes **Network > Routers > Omada setup** and copies the assigned `omada://...` Inform URL. In standalone TP-Link EAP management, set **Controller Inform URL** to this exact value (or request assistance). If the AP is managed by another controller, migrate/release it safely first. Power it and provide internet access on its uplink. An Omada controller operator must then **adopt/approve** the device in that customer's site.
5. On Django VPS, run `python manage.py poll_omada_managed`. Refresh the customer's **Routers** page and **Dashboard**. You should see **Connected** from Open API, with a fresh check time. Disconnect the AP and re-check to see **Offline**; if older than two minutes, it says not recently verified.
6. Sign in as another business and verify the first business's MAC, router name, Inform URL and status do not appear.

**Do not collect live Wi-Fi payments from this new account yet.** Connection only proves AP adoption, not that a paid client can be authorized. A per-site captive portal, access rules, a verified per-business Omada authorization target, account isolation, EvPay submerchant/settlement approval, and a real end-to-end charge-to-internet test are still required to safely expand beyond Eaglelink.

### Router adoption notes

- If the AP is behind an ISP router or CGNAT, it normally reaches the VPS **outbound** via its controller inform connection; the customer does not need to buy a public IP or create a VPN. Check firewall/ISP permissions and model compatibility.
- A current connection is shown only when the **same approved AP MAC** is visible inside the staff-assigned **Open API siteId**. A manual WorldLink review by itself never displays Connected.
- Do not confuse the **controller's** `omadacId` in the hotspot operator API with a **site's** device Inform URL `omadacId`. The public Inform URL must be copied from that target site and verified on the AP.
- If the customer's device has never been adopted, follow the model's Omada user guide to configure Controller Inform URL. Staff remains responsible for site provisioning, SSID/portal setup, adoption and testing.
- Do not open controller management (`8043`) or Omada databases (`27017`) to the general internet. Review exposure of `8088`, which also serves controller HTTP management on some versions; pre-auth captive portal access requires its own secure network configuration before general rollout.

## Rollback and scope

The migration adds only an Omada site table, an optional site link on an existing setup request, and a new central connection-mode choice. It does not modify existing vouchers, historical payments, wallet totals, or the Eaglelink payment pilot gate. If you must revert the web code, do not delete the new database tables without a separate recovery plan; restore previous application code while leaving the additive migration applied.
