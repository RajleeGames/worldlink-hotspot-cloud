# WorldLink Hotspot Cloud v0.6 · Dedicated operations console

## What's new

- Two login choices at `/login/`: **Business** or **WorldLink Team**. Choosing WorldLink Team does not grant access. A user must already have the required staff permissions. Staff-only accounts cannot use the business portal, and tenant accounts cannot enter the WorldLink console.
- **WorldLink Control Center** at `/console/`, using exactly the same `static/css/app.css` and shell as the customer workspace.
- Team directory, invitation creation, support/manager roles, per-account disable/enable, audit entries, re-issue invitations and read-only details.
- Staff accounts are never created from public signup. A WorldLink Super Admin can appoint platform managers; platform managers may invite only support staff. Staff members cannot manage their own roles. Only the Super Admin can change platform branding.
- One-use, 48-hour setup links. The raw token is **never stored** in the database; its SHA-256 digest is retained. Setup links are displayed once to the issuing administrator, who must share them securely. No default or shared password is generated.
- Business creation, invite-new-owner functionality, add-an-existing-business-member, logo/favicon management from the HTML console.
- WorldLink `/admin/` retained as technical fallback for the Super Admin. Team members should use `/console/`.
- Additional tests for role boundaries, login portal, one-time invitation and tenant access.

## Important security and launch notes

Do not use this version to sell internet access until RADIUS/Omada authentication and accounting are integrated and live router tests pass. Payment verification is also not connected. Invitation links must only be shared privately. For production, configure HTTPS, strong secret key, PostgreSQL, restricted public signup, SMTP invitations, MFA for administrators, login throttling, backups and security review.

The public business signup page remains controlled by `ALLOW_PUBLIC_SIGNUP` in `.env`. **It never creates WorldLink staff accounts.** In production, set `ALLOW_PUBLIC_SIGNUP=False` and onboard business owners from the console.

### Owner account setup

Only the first **WorldLink Super Admin** must be bootstrapped using Django's `createsuperuser` command. Do not reuse a credential from other websites. Sign in using the **WorldLink Team** tab. Thereafter, invite other team members from `/console/team/invite/`. The invitations are redeemed by the invited people, who choose their own passwords.

### Upgrade from v0.5

1. Back up the database and media folder before running migrations.
2. Extract the v0.6 ZIP over `C:\Users\user\worldlink-projects\worldlink-hotspot-cloud`. It deliberately excludes `.env`, `db.sqlite3` and `media/`.
3. Install requirements (unchanged) and run `manage.py migrate`, `manage.py check`, `manage.py test`.
4. Run `manage.py runserver`; open `http://127.0.0.1:8000/login/?portal=staff`.

### Access levels

| Role | Read platform | Change companies | Invite support staff | Appoint managers | Change platform branding |
| --- | --- | --- | --- | --- | --- |
| Super Admin (superuser) | Yes | Yes | Yes | Yes | Yes |
| Platform Manager | Yes | Yes | Yes | No | No |
| Support Staff | Yes | No | No | No | No |
| Business Owner/User | No | Own business only | No | No | No |

Invite links should be copied privately and are never emailed automatically by this version. SMTP-based delivery and multi-factor authentication are sensible next security upgrades.
