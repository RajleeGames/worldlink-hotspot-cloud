# WorldLink Hotspot Cloud — Multi-business onboarding and live-payments phase

This release is designed for a **controlled rollout**. It does not switch on paid Wi-Fi for all new businesses. It preserves the existing Eaglelink pilot and introduces independent WorldLink reviews for additional central-Omada access points.

## What changes

- **Owner / technician:** `Routers → Add router → Omada setup`. Device registration is mobile-friendly. Submit AP MAC, SSID, serial, and optional non-secret notes. No VPN, Tailscale, or Omada operator password is required from a customer using WorldLink's central controller.
- **WorldLink staff:** `Control Center → Router onboarding → Open review page`. A dedicated review page shows customer details and separate fields for central Omada site name, Inform URL `omadacId`, and Open API `siteId`. The staff account and connection status are independently checked.
- **WorldLink staff:** after site assignment and *fresh connected AP observation*, confirm merchant/provider permission to collect on behalf of the business and a real-device external-portal test. Only then record the distinct per-AP **Live payment approval**. There is a revoke button. All decisions are audited.
- **Finance:** each business sees provider-confirmed EvPay receipts, unsettled receipts, cleared wallet balance, and pending withdrawals on its main dashboard. Confirmed EvPay revenue is **not** a withdrawable balance. WorldLink finance staff must independently clear each settlement; withdrawal requests remain manual and use independently verified destinations.
- **Business payments:** live checkout and automatic paid-client authorization can recognize multiple, separately approved central Omada APs, but only if *all* controls below are satisfied.

## Safe activation prerequisites for each new business

1. Confirm the WorldLink EvPay merchant agreement **expressly permits collections on behalf of this business and manual onward settlement/payout**. Do not claim this feature is approved by EvPay from technical API success alone.
2. Confirm the business account is **ACTIVE** and its site exists on the trusted central Omada controller. Each business must have an isolated site. Configure the site's guest Wi-Fi and external portal redirect to `https://wifi.worldlinksecurity.co.tz/wifi/<business-slug>/` with the corresponding required walled-garden access. Ensure the trusted WorldLink Hotspot Operator can authorize the new site; never give tenants that operator credential.
3. In the dedicated WorldLink review page, assign the Omada *Inform* site ID and the separate *Open API* site ID. No passwords or API secrets belong in the browser form.
4. Adopt and check the **physical** AP. From the existing Django VPS run `python manage.py poll_omada_managed`. It must report **Connected**, and the WorldLink review page must show a **fresh** connected observation.
5. Confirm that the phone/payment test reaches the correct business portal and exact approved AP/SSID. WorldLink authorized staff then check **both** attestations and approve this device for live payments.
6. Update the main Django VPS `.env` (not the new Omada VPS): include the new business ID in `EVPAY_COLLECTION_COMPANY_IDS`, retain the existing Eaglelink ID until a completed cutover, and add `EVPAY_MULTITENANT_ENABLED=True`. This is intentionally **False** by default. Restart the Django and payment worker processes to load these settings.
7. Activate a *small* verified real-money test; confirm the provider status **SUCCESS** or **SETTLED**, accepted webhook or verified reconciliation, automatic Omada activation, correct expiry, tenant-only dashboard earnings, finance queue clearance and withdrawal request status. Do not assume a successful EvPay PIN entry means provider confirmation.

**Payment permission requires all of:** global EvPay/Omada settings; the exact company in the explicit allowlist; `EVPAY_MULTITENANT_ENABLED=True`; active business; reviewed isolated central site; staff-only per-router live approval; and exact AP MAC and SSID. These are rechecked before initiating a customer charge **and** before authorizing paid internet.

## Do not delete Eaglelink yet

Only one physical EAP225 is currently available. The same AP cannot simultaneously demonstrate two independent live business sites. For signup testing, create a second business and use a clearly labelled *dummy/offline* AP MAC to test the administrative forms and team review. Never mark it as connected or approve live payments.

For a **real cutover** to a new business, schedule downtime, let existing Eaglelink purchases expire, preserve backups and order history, revoke old live authorization, move/adopt the physical AP to the intended Omada site and SSID, verify the new AP/site connection, and only then enable that exact new business for payment. Do **not** delete the old router/account to start testing; historical payments, audit logs and receipts must remain available.

## VPS deployment order (after code is pushed to GitHub)

On the old Django VPS in `/var/www/worldlink-hotspot-cloud`, with `.venv` activated:

```bash
git status --short
git pull --ff-only
python manage.py check
python manage.py migrate --plan
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart worldlink-hotspot.service worldlink-evpay-fast.service worldlink-evpay-omada.service
sudo systemctl is-active worldlink-hotspot.service worldlink-evpay-fast.service worldlink-evpay-omada.service
```

Back up the **real** production database and `.env` before applying migrations. Existing SQLite DB is outside the Git checkout at `/var/lib/worldlink-hotspot-cloud/db.sqlite3`; prefer the verified SQLite online-backup method used previously. Do not put `.env`, DB backups, controller credentials, or tokens in Git.

Do not enable the multi-tenant flag until the first new site has completed all approval steps. No new Omada VPS deployment is required for this release; Omada stays on its dedicated server.

## Remaining release gates before unrestricted public advertising

- Provider written approval for third-party collections/settlement, documented refund/dispute and chargeback procedures.
- End-to-end new-business *physical* AP and genuine EvPay transaction tests after the code is deployed.
- Monitoring/alerting for controller offline, worker failures, callback 401s, pending authorizations and delayed settlements; tested backups and restores.
- Written finance reconciliation and payout SLA. Never treat EvPay `SUCCESS` as independently cleared funds. Reversals of previously credited settlements require a manual finance incident/reconciliation procedure before withdrawals.
- Rotation of any Django, EvPay, and Omada secrets that were ever copied into chat, screenshots or shared terminals. Keep secrets in protected server configuration, not in router setup pages.
- MikroTik remains a separate RouterOS pilot for checking and synchronizing **manually sold** vouchers; it does **not** gain automatic EvPay/USSD authorization in this change.
