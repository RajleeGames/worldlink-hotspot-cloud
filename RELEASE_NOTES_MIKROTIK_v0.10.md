# WorldLink Hotspot Cloud — MikroTik router pilot v0.10

This is an **incremental patch on top of the wallet v0.9 patch**. The ZIP
contains only a Git patch — no database, passwords, uploads, or .env.

## Owner workflow

1. Open **Network → Routers → Add router**. If no location exists, saving
   your first router automatically creates a "Main site" location.
2. Select MikroTik, enter the router's management IP and HTTPS port (443).
3. Select **Connect & sync**, enter a dedicated RouterOS login and password.
   These credentials are used for ONE request and not saved in the database.
4. Select **Test connection**. The page checks RouterOS version and that the
   built-in HotSpot is enabled. It does not modify router settings.
5. After a voucher is genuinely sold through the manual-sale flow, select
   **Sync up to 10 sold vouchers**. The router receives only vouchers in the
   SOLD state with a recorded manual sale.
6. A customer connects to the guest SSID and enters the printed code as
   both username and password on the **MikroTik HotSpot login** page.
7. Use **View live users** on the same router page to read the current
   MikroTik HotSpot Active table. The snapshot is read-only and not a
   persistent, automatically refreshing session monitor.

The adapter creates a dedicated hotspot user and associated plan profile,
using your plan's bandwidth, shared-user count, accumulated uptime and
optional total traffic limit. Sync is idempotent and capped at ten vouchers
per request; repeat for larger queues. Router users/profiles not owned by
WorldLink are not modified.

**No unpaid checkout request, unverified EvPay payment, READY voucher or
test-payment transaction is authorized for internet access.**

## Prerequisites for the physical router test

- A real MikroTik gateway with **RouterOS v7**, correctly connected to the
  internet and with a **HotSpot server enabled** on the guest bridge.
- RouterOS www-ssl (REST over HTTPS) enabled; restrict it to a trusted private
  LAN/VPN and NEVER expose it to the public internet.
- A dedicated RouterOS account with permission to inspect and create HotSpot
  users/profiles; a trustworthy HTTPS certificate.
- The Windows Django PC or VPS must have a private network route to the
  router management IP. For 4G/5G SIM and CGNAT, a private VPN is usually
  necessary for a remote VPS.
- In the existing .env, add, for example:

      MIKROTIK_ALLOWED_CIDRS=192.168.88.1/32

  Replace that sample IP with the ACTUAL router management IP. Restart Django
  to pick up the change. The default empty setting BLOCKS connections.
  Multiple allowed IPs can be comma-separated.
- For your own trusted router CA certificate, set MIKROTIK_CA_FILE to a PEM
  path accessible on the Django host. By default, HTTPS validates using the
  host CA store. In a strictly local DEBUG test, you may manually opt out of
  TLS validation using the checkbox. Production cannot disable validation.

Omada and Cudy cannot use this MikroTik connector without separate vendor
integration. Do not change the router family to trick this restriction.

## Scope and limitations

- **No physical router connection was tested in the development environment.**
  The code was exercised against simulated RouterOS REST responses and
  Django's test database only. Test on the customer's hardware before launch.
- WorldLink's hosted checkout is still a payment request page; it is not
  the router's captive-login endpoint. MikroTik handles login locally.
- No live automatic EvPay pay-to-connect or continuous router polling.
  Manual read-only HotSpot Active snapshots are supported.
- Uptime limits mean total CONNECTED time, not wall-clock time since first
  login. No automatic expiry on a fixed calendar date is provided.
- The guest Wi-Fi must have no bypass path around the hotspot gateway.

## Safe installation — Windows, original project folder ONLY

Stop Django and open the existing folder:

    cd "C:\Users\user\worldlink-projects\worldlink-hotspot-cloud"

1. Make a verified SQLite backup with sqlite3.backup() as instructed in
   the accompanying answer. Do not overwrite your current db.sqlite3.
2. Download the v0.10 patch ZIP to Downloads.
3. Extract it into that SAME project directory. It contains only
   worldlink_hotspot_mikrotik_v010.patch, no project tree.
4. Run the safety check first:

    git apply --check .\worldlink_hotspot_mikrotik_v010.patch

   STOP if there is an error. Do not force the patch onto different code.
5. Only after that check passes, apply:

    git apply .\worldlink_hotspot_mikrotik_v010.patch

6. Run your same venv's manage.py migrate, check and test networks.tests.
   Then restart Django. The migration only ADDS management port/last-check
   fields and a voucher-sync table; it does not replace existing data.

No GitHub push, new project directory, database copy or new user account
is necessary. Your current wallet, users, sessions, vouchers, uploaded
media, .env and Git history remain in the same project.

## Hardware acceptance test before the customer pays

1. Connect the customer's router to the SAME private network as Django,
   or to an approved VPN; verify its management IP and HTTPS certificate.
2. Test connection and verify an actual RouterOS model/version is returned.
3. Create one test-package voucher and manually record a genuine voucher
   sale; sync it with the dedicated router login.
4. Connect a separate phone to guest Wi-Fi. Test the sold code as login.
5. Check it appears in RouterOS HotSpot Active. Test an unpaid/READY code
   and verify that one cannot get internet.
6. Test upload/download limits, data cap, cumulative uptime and users
   returning after disconnection.

Official MikroTik references:
https://help.mikrotik.com/docs/spaces/ROS/pages/47579162/REST+API
https://help.mikrotik.com/docs/spaces/ROS/pages/56459266/HotSpot+-+Captive+portal
