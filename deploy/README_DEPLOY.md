# WorldLink Hotspot Cloud — VPS pilot deployment kit

Target: wifi.worldlinksecurity.co.tz / VPS 31.97.52.238 / service worldlink-hotspot.service / gunicorn 127.0.0.1:8095 / Django config.wsgi:application.

## 0. Before pushing on Windows

From the existing source project root:

```powershell
cd C:\Users\user\worldlink-projects\worldlink-hotspot-cloud
.\.venv\Scripts\python.exe deploy\patch_settings.py
.\.venv\Scripts\python.exe manage.py check
# Verify secrets remain ignored. If Git exists:
git status --short
git check-ignore .env db.sqlite3
```

Use a **private GitHub repository** `RajleeGames/worldlink-hotspot-cloud`. Push code only, not `.env`, `db.sqlite3`, backup files, or `media/`.

If new repo, create it empty on GitHub first, then in your project folder use `git init -b main; git add .; git diff --cached --name-only; git commit -m "Initial WorldLink Hotspot Cloud"; git remote add origin https://github.com/RajleeGames/worldlink-hotspot-cloud.git; git push -u origin main` after configuring Git authentication. If Git is already initialized, do not run `git init` or replace the remote.

## 1. Configure DNS

Cloudflare DNS for `worldlinksecurity.co.tz`: A record `wifi` → `31.97.52.238`. Use **DNS only** temporarily for certificate issuance, then proxied after origin TLS is confirmed. Check for conflicting CNAME/AAAA `wifi` records. Do not change DNS for other subdomains.

## 2. Prepare VPS

```bash
ssh miraji@31.97.52.238
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx
sudo install -d -o miraji -g miraji -m 755 /var/www/worldlink-hotspot-cloud
sudo install -d -o miraji -g www-data -m 750 /var/lib/worldlink-hotspot-cloud
sudo install -d -o miraji -g www-data -m 750 /var/lib/worldlink-hotspot-cloud/media
sudo install -d -o miraji -g miraji -m 700 /var/backups/worldlink-hotspot-cloud
```

### GitHub access to a private repo

Generate a separate read-only deploy key, only if your VPS doesn't already have working read access to this repo:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/worldlink_hotspot_deploy -C 'worldlink-hotspot-vps' -N ''
cat ~/.ssh/worldlink_hotspot_deploy.pub
```

Paste the **PUBLIC** key into GitHub repo Settings → Deploy keys (read-only). Add an SSH host alias (don't overwrite any other SSH config):

```bash
cat >> ~/.ssh/config <<'EOF'
Host github-worldlink-hotspot
    HostName github.com
    User git
    IdentityFile ~/.ssh/worldlink_hotspot_deploy
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T github-worldlink-hotspot
```

Clone using `git@github-worldlink-hotspot:RajleeGames/worldlink-hotspot-cloud.git`. If the repo is public, the normal HTTPS URL works too, but a private repo is recommended.

```bash
# Target directory must be empty; git can clone into the existing empty directory.
git clone git@github-worldlink-hotspot:RajleeGames/worldlink-hotspot-cloud.git /var/www/worldlink-hotspot-cloud
cd /var/www/worldlink-hotspot-cloud
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install 'gunicorn>=23,<25'
```

## 3. Set persistent production environment

Copy `deploy/.env.vps.example` to `.env` (`cp ... .env`) and edit the new `.env` using `nano` with a **new production Django secret**. Rotate secrets previously exposed in chat. It must contain the real **sandbox** API credentials and a strong webhook route token; never commit it.

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'  # for DJANGO_SECRET_KEY
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'  # for EVPAY_WEBHOOK_TOKEN
cp deploy/.env.vps.example .env
chmod 600 .env
nano .env
```

If you need existing local users/businesses, copy **db.sqlite3** and uploaded `media/` from your Windows project into `/var/lib/worldlink-hotspot-cloud/` BEFORE running migrations. Otherwise start a fresh database and create users/company on the VPS. Remember to set `EVPAY_COMPANY_ID` to the actual pilot company primary key; don't assume it is 1.

```bash
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py check --deploy
```

Review any deployment warnings; HSTS is deliberately 0 until TLS is verified.

## 4. Install separate service + Nginx site

```bash
sudo cp deploy/worldlink-hotspot.service /etc/systemd/system/worldlink-hotspot.service
sudo systemctl daemon-reload
sudo systemctl enable --now worldlink-hotspot.service
sudo systemctl --no-pager status worldlink-hotspot.service

sudo cp deploy/nginx-worldlink-hotspot.conf /etc/nginx/sites-available/worldlink-hotspot
sudo ln -s /etc/nginx/sites-available/worldlink-hotspot /etc/nginx/sites-enabled/worldlink-hotspot
sudo nginx -t
sudo systemctl reload nginx
```

Test Gunicorn and Nginx:

```bash
sudo ss -ltnp | grep ':8095'  # make sure no other service already owns it
curl -sSI -H 'Host: wifi.worldlinksecurity.co.tz' http://127.0.0.1:8095/login/
curl -sSI --resolve wifi.worldlinksecurity.co.tz:80:127.0.0.1 http://wifi.worldlinksecurity.co.tz/login/
```

Issue a certificate when DNS `wifi` resolves to your origin and HTTP port 80 is reachable:

```bash
sudo certbot --nginx -d wifi.worldlinksecurity.co.tz
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Verify `https://wifi.worldlinksecurity.co.tz/login/` then enable Cloudflare **Proxied** and SSL/TLS **Full (strict)** if compatible with your existing origin-host configurations. Do not globally switch TLS mode without checking existing site certificates.

## 5. Test payment sandbox on VPS

- `.env`: `EVPAY_ENVIRONMENT=sandbox`, `EVPAY_BASE_URL=https://api-uat.evpay.co.tz`, `EVPAY_PRODUCTION_CHARGES_ENABLED=False`.
- VPS authentication requests now originate from whitelisted VPS public egress IPv4 (verify with `curl -4 https://api.ipify.org`).
- Open `/payments/evpay/` as pilot company OWNER/MANAGER, test **authentication first**.
- Verify HTTPS webhook route exists, but do not send it unsigned fake `payment.succeeded` events. A 401 response to an unsigned request is expected.
- Submit only simulated sandbox payments. Check status reconciliation and signed callbacks before router activation.
- If UAT still blocks, ask EvPay to allow the actual outbound IPv4 and inspect Cloudflare Ray ID. An IPv6 egress may differ from the IPv4 allowlist.

## 6. Updates after pushing from VS Code

```bash
cd /var/www/worldlink-hotspot-cloud
bash deploy/update.sh
```

It backs up SQLite with Python's online backup API, runs `git pull --ff-only`, `pip install`, `migrate`, `collectstatic`, and restarts **only** `worldlink-hotspot.service`.

## Notes

- The v0.8 EvPay integration is only a single-company pilot lab; it does **not** grant router internet access, offer general multi-merchant settlement, or handle merchant payouts.
- Hosted public login and webhook endpoints are exposed to the internet. Keep public signup disabled, use strong private credentials, rotate previously exposed secrets, and limit access to trusted testers during the pilot.
- SQLite works for a pilot, but has limited write concurrency. Monitor `database is locked`, schedule backups, and migrate to PostgreSQL before broad customer use.
- Invitation emails require real SMTP credentials; this starter does not configure SMTP for production.
- Never `git reset --hard` the VPS during deployment or overwrite the `.env`/SQLite database/media.
