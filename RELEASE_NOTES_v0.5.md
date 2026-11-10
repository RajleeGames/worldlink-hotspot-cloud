# WorldLink Hotspot Cloud v0.5 — Sessions & Control Center

## What's new
- Tenant-scoped Wi-Fi customers: create, edit, delete (only without session history), details and history.
- Session model: MAC, IP, account username, customer, router, plan, voucher, start/expiry, heartbeat, bytes and source.
- Connected Users: filters, search, CSV export, expiry countdown, online/recorded/demo summaries, responsive layout.
- WorldLink Control Center: all businesses, logins, subscriptions, router and customer totals, session statistics, status management and audit log.
- Permissions: WorldLink employees need explicit platform permissions; business users cannot access other tenants or the WorldLink console.
- A trusted adapter service contract and clearly labeled demo seed command.
- Same `static/css/app.css` and `static/js/app.js` as the earlier UI.

## Important limitations
**No network router is integrated yet.** This release does not authenticate real Wi-Fi users, disconnect them, or automatically receive accounting updates. Records marked DEMO never count online; RADIUS/Omada observations only count online when a trusted adapter actually supplies them, with a fresh heartbeat and active, unexpired session. Payment provider integration is still pending.

## Install
Follow README.md, Section "v0.5". Run `manage.py migrate`, `check` and `test` using your `.venv` Python. Do not delete `db.sqlite3`, `.env`, or media.

## Next engineering step
MikroTik RADIUS integration: authenticated NAS registry, FreeRADIUS accounting events, CoA/disconnect, voucher activation, accurate time/data cutoffs, retries, secure secrets and tests with a real router. Then implement Omada controller adapter and provider-verified mobile payments.
