# WorldLink: customer UI + mobile release

This release completes the English/Swahili and mobile-input work alongside a clean navigation, voucher sales, dashboard, and router-onboarding layout.

## Changes

- Compact navy/teal sidebar, lighter card spacing, and cleaner business dashboard labels.
- Remove the repeated connectivity notice from every customer dashboard page. Operational approvals and permission checks remain unchanged.
- Voucher batch table now links to a separate **Record voucher sale** page. Business staff select cash, bank, or other verified payment there; authorization, tenant isolation, one-sale-only rules, and CSRF protection remain enforced. Manual sales are **not** EvPay funds.
- Omada requests show **You submit** and **WorldLink reviews** checklists, plus existing per-router status and connection details.
- Public portal messages are shorter, and its first mobile render has a self-contained layout fallback for captive browsers that delay the CSS request.
- All dashboard, authentication, and captive-portal input controls use iOS-safe 16px text on mobile. Browser accessibility zoom remains enabled.

## Deploy from GitHub on the Django VPS

1. Merge/push the tested release to the repository from the development computer.
2. On the Django VPS run, one command at a time:

   ```bash
   cd /var/www/worldlink-hotspot-cloud
   source .venv/bin/activate
   git status --short
   git pull --ff-only
   python manage.py check
   python manage.py collectstatic --noinput
   sudo systemctl restart worldlink-hotspot.service
   sudo systemctl is-active worldlink-hotspot.service
   ```

   Resolve any existing VPS edits before pulling. No migrations are required for this update.

## Customer acceptance checks

1. On an iPhone, open the WorldLink sign-in page and focus a username/password field: the whole page should not zoom.
2. Open the live guest Wi-Fi captive portal from a fresh connection. Check that the logo, title and package cards fit the phone on the first load, then test a voucher-code field.
3. Sign in to a business account. Check the sidebar at phone and desktop sizes, and open the voucher batch page.
4. Choose **Record sale** for a READY voucher. Check that its method selector opens normally on the new page, confirm one genuine offline sale, and verify a second attempt cannot resell the same code.
5. Open **Router setup** to verify the customer details and WorldLink review checklist.

## Not part of this release

The TZS 20,000/month subscription, recurring billing, and live EvPay collection prompt are **not** enabled by this UI patch. Those require a separate billing model, business-level checks, webhook reconciliation, and confirmation that the provider is reachable. Do not treat a saved manual payment method as a live EvPay integration.
