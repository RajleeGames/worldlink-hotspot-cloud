# WorldLink Router Onboarding — Phase 1

This is an **additive, database-migrated** update to the existing WorldLink Hotspot Cloud. No existing tenant, router, package, voucher, payment, or wallet record is deleted or migrated into a new table. The original Eaglelink Omada live pilot is unchanged.

## What it delivers

- Owners/managers/technicians may register a TP-Link Omada access point under **Network → Routers**. They can save a draft or request private setup assistance, independently for every company.
- The new **Omada setup** screen captures only connection metadata: optional private controller URL, controller ID, AP MAC, guest SSID, and non-sensitive support notes. It does **not** request or store router/controller credentials.
- An owner can see whether their request is Draft, Awaiting review, Needs info, or Details reviewed. Changing a reviewed request returns it to draft/submitted status.
- The **business dashboard** now shows its own registered Omada router count, controller ID, and onboarding state. It never includes another company's routers or controller details. The online status is explicitly marked *unverified* until an authenticated device-status integration is available; merely pasting an ID does not mean the EAP has been adopted.
- Authorized WorldLink staff use **Control Center → Router onboarding** to review requests, ask for details, or mark the intake reviewed. All actions are scoped and permission checked; staff decisions create audit records.
- Existing MikroTik v7 HTTPS REST pilot workflows remain unchanged.

## What it does *not* deliver yet

- It does not configure devices automatically, create a remote VPN or local agent, discover or authorize new Omada APs, validate controller operator credentials, or activate a paying customer on newly registered routers.
- `REVIEWED` means **intake details reviewed**, not connected, authenticated, or approved for live sales.
- The existing `.env`-controlled EvPay/Omada activation code remains restricted to the previously approved pilot company. **Do not enable new companies in live collection flags just because an onboarding request was reviewed.**
- This does not enable universal "any router" support. Each device family needs its own tested integration and security model.

## Apply on Windows development machine

From `C:\Users\user\worldlink-projects\worldlink-hotspot-cloud`, after checking `git status --short`:

```powershell
git apply --check "C:\path\to\worldlink_router_onboarding_v1_PATCH.patch"
git apply "C:\path\to\worldlink_router_onboarding_v1_PATCH.patch"
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
git status --short
```

Check the diff before committing, then push the code to GitHub as normal. **Do not apply this same patch directly on the VPS after pulling the commit**; that would apply it twice.

## Safe VPS deployment, once code is pushed

Back up the SQLite database first (you previously used SQLite's consistent backup API), then:

```bash
cd /var/www/worldlink-hotspot-cloud
source .venv/bin/activate
git status --short
git pull --ff-only
python manage.py check
python manage.py migrate --plan
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart worldlink-hotspot.service
sudo systemctl is-active worldlink-hotspot.service
```

There is **one new migration**: `networks.0003_omada_onboarding`. No `.env` changes and no payment/webhook/service restarts are required beyond the normal web deployment. Existing `worldlink-evpay-fast.service` and `worldlink-evpay-omada.service` stay enabled for the pilot.

## Verification without real money

1. Log into a test business as owner, add an Omada router, select a location, and save.
2. You should land on **Omada setup**. Enter connection details or request assisted help; submit the form.
3. Open WorldLink Control Center as authorized platform staff and review the request; see that the owner receives the updated status.
4. Confirm another business cannot open or modify the first router's setup URL.
5. Verify Eaglelink's already working live payment + Omada activation flow separately **without doing unnecessary repeated real-money tests**.

## Security before public launch

Production credentials were previously printed in a console/chat. Rotate Django, EvPay API/signing, webhook, and Omada operator secrets in a coordinated maintenance window; changing one side without updating the other can interrupt live payments. Keep secrets out of terminal screenshots, source patches, GitHub, and setup notes. Use a separate encrypted credential handoff for future router connectors. Never expose Omada port 8043 or MikroTik RouterOS REST directly to the public internet.

## Next phase

Build a per-company approved connector/agent with authenticated outbound communication, verified controller identities, per-router payment-to-client binding, strict tenant-scoped processing, and explicit live activation approval. Then integrate settlements and withdrawal ledgers with verified provider settlement (do not treat a successful charge as cleared withdrawable funds).
