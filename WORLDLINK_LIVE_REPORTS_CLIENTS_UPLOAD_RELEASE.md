# WorldLink: live sales, clients, wallet clarity and uploads

This release adds **reported facts only** and does not activate an unapproved AP.

## What customers and businesses see

- Sales reports: All / cash & bank vouchers / verified EvPay. Pending or failed USSD requests never count as revenue. Tenant boundaries remain enforced.
- Wi-Fi customers: verified EvPay payments and their actual names/phones, plus the separate existing saved contacts directory. A transaction is not misrepresented as a unique person.
- Connected users: only online Omada clients from a recently polled, staff-reviewed AP at the correct dedicated site and SSID. MAC/IP and optional controller-supplied device type are shown; identity and expiry are joined only from genuinely activated, unexpired payments/vouchers.
- Wallet: automatically displays verified EvPay sales and provider-settled amounts. **Withdrawable** increases only on independently confirmed WorldLink cleared funds; WorldLink staff must record the actual settlement reference. Never pay out based on a `SUCCESS` alone.
- Forms: duplicate-click lock and processing state across POST forms. Image-upload forms use actual transferred bytes for a 0–100% progress bar, followed by a separate processing state. Progress during an EvPay USSD prompt is indeterminate: there is no honest percentage available.
- Company and platform logos: incoming PNG/JPEG/WebP/GIF under 15 MB and 24 megapixels are normalized to a centered 512 × 512 transparent PNG, preserving the logo rather than cutting off text. Original uploads are not saved.

## Deploy on main Django VPS

```bash
cd /var/www/worldlink-hotspot-cloud
source .venv/bin/activate
git status --short
git pull --ff-only
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart worldlink-hotspot.service worldlink-evpay-fast.service worldlink-omada-managed.service
sudo systemctl is-active worldlink-hotspot.service worldlink-evpay-fast.service worldlink-omada-managed.service
python manage.py poll_omada_managed
```

If `git pull --ff-only` refuses due to local edits, **do not discard them**. Preserve them and inspect the conflict first. Deploy when production is quiet; the migration is additive.

## Verify live Omada clients

The existing `worldlink-omada-managed.service` polls the controller every 30 seconds. To test the client API without showing credentials or guest personal information:

```bash
python manage.py shell -c "from networks.omada_monitor import OmadaReadOnlyClient; from networks.models import OmadaManagedSite; site=OmadaManagedSite.objects.get(company_id=2); clients=OmadaReadOnlyClient().get_connected_clients(site_id=site.openapi_site_id); print('READ-ONLY OMADA CLIENTS:',len(clients))"
python manage.py shell -c "from hotspots.models import OmadaClientObservation as C; print('RAHA OBSERVED:',C.objects.filter(company_id=2).count())"
```

If the client API rejects this read, enable only the **read-only clients permission** for the existing WorldLink Open API account; this must never be solved by adding operator passwords to business forms. The AP monitor continues and stale client observations go offline. The site must be mapped to a reviewed AP with the exact MAC/SSID.

## EvPay settlement vs business withdrawal

EvPay's API defines `SUCCESS` as customer money received but not yet merchant-settled; `SETTLED` as settled into the EvPay merchant account. The reconciliation worker now follows successful references until a settled state arrives and periodically checks recent settlements for reversals. It never starts a new charge. Neither stage proves an independent WorldLink bank deposit. Funds enter `BusinessWallet.available` only when authorized WorldLink finance staff records a verified settlement evidence reference. **Do not manually mark uncleared provider payments as withdrawn.**

## Verify without charging a customer

```bash
python manage.py test cloud.test_revenue_reports hotspots.test_live_omada_clients cloud.tests.BrandingTests payments.test_live_collections
```

After deployment, log in to the test business: `Sales → Sales reports`, `Network → Connected users`, `Network → Wi-Fi customers`, `Business settings`, and `Money & withdrawals`. Use a PNG/JPG logo >2048 px to verify resize. When EvPay is available, conduct one low-value live test with consent and verify its single reference and eventual status; do not repeat USSD charges solely to test a loading spinner.
