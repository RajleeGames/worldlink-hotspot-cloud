# WorldLink English / Swahili + mobile launch update

This update changes user-interface copy and mobile styling only. It does **not**
change tenant permissions, EvPay secrets, Omada authorizations or payment status.

## What changes

- The business dashboard's `EN` / `SW` selector continues to save language in
  the signed-in session. New router onboarding, WorldLink approvals, payment
  history, manual requests and EvPay test-lab labels now use the same translation
  catalog. Existing translated pages remain available.
- The public guest portal's `EN` / `SW` selector translates the live mobile-money
  checkout and confirmation states. A successful voucher redemption now keeps
  the chosen language.
- Text inputs, selects and textareas are at least **16px on mobile** to stop
  iPhone Safari automatically zooming the page when the keyboard opens.
  Touch targets and small-screen onboarding readability are improved. Pinch zoom
  stays available for accessibility.
- Tenant-entered names, plan names, SMS/provider messages, arbitrary form-error
  text and custom portal terms are **not** machine-translated. Businesses should
  provide their own localized public descriptions/terms if needed.

## Local GitHub release

1. Apply the supplied `.patch` to a clean copy of the same repository version.
2. Run `python manage.py check` and
   `python manage.py test portal.tests portal.test_launch_language
   payments.test_live_collections networks.test_omada_live_payments
   vouchers.test_live_redemption` (as a single command).
3. Inspect `git diff --check`, `git diff --stat`, then commit and push normally.

## Existing WorldLink web VPS (not the Omada controller VPS)

```bash
cd /var/www/worldlink-hotspot-cloud
source .venv/bin/activate
git status --short
git pull --ff-only
python manage.py check
python manage.py test portal.test_launch_language
python manage.py collectstatic --noinput
sudo systemctl restart worldlink-hotspot.service
sudo systemctl is-active worldlink-hotspot.service
```

No migrations are required by this update. Preserve any local modifications
before pulling; do not force-reset your VPS worktree.

## Real-phone acceptance checks

1. iPhone, on `RAHA-WIFI`: load the captive portal, switch **SW**, focus the
   voucher and phone-number fields, and confirm the keyboard opens **without
   page zooming or sideways overflow**. Pinch zoom must still work.
2. Switch to **EN**; confirm button wording, package price, customer identity,
   number and voucher references are correct.
3. Sign in as a business owner: switch `SW` and review packages, vouchers,
   payments, and router setup on a narrow phone screen. Switch back to `EN`.
4. Sign in as WorldLink staff: verify the Omada review page fits on mobile and
   shows correct business/AP/SSID identifiers in both languages. Do **not**
   approve or retire a real AP merely to test translation.
5. Verify the existing voucher and the authorized customer Wi-Fi route still
   work. Only attempt a *new* paid USSD test once the provider's status API and
   callback are healthy and outstanding payments are reconciled.

## Public launch gates

- Resolve EvPay HTTP **523** outages and reconcile any `PENDING` / `UNKNOWN`
  collection (including the previously observed RAHA payment #11) before
  encouraging new paid purchases. Never mark payment successful on a screenshot.
- Keep per-business Omada hardware verification and payment approvals. Do not
  bypass the live-collection allowlist or turn on unrestricted auto-approval.
- Verify receipt, internet activation, expiry, account attribution, and wallet
  accounting for at least one real approved business end to end.
- Rotate any production secrets that have been pasted into chats, terminals or
  shared screenshots; check monitoring, backups and provider support channels.
