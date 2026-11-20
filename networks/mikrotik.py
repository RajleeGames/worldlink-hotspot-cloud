"""Small, HTTPS-only RouterOS v7 REST adapter for an on-site MikroTik pilot.

Router credentials are accepted for a single request and are never persisted.
The administrator must explicitly allow-list router management IPs in .env.
"""
import base64
import ipaddress
import json
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.conf import settings


class RouterConnectionError(Exception):
    """Safe, actionable message that never contains a router password."""


def require_allowed_router_ip(address):
    try:
        ip = ipaddress.ip_address(address)
    except (ValueError, TypeError):
        raise RouterConnectionError("Save a valid router management IP address first.") from None
    ranges = settings.MIKROTIK_ALLOWED_CIDRS
    if not ranges:
        raise RouterConnectionError(
            "Router connections are disabled. WorldLink's administrator must set "
            "MIKROTIK_ALLOWED_CIDRS to the exact router LAN/VPN IP (for example 192.168.88.1/32)."
        )
    if ip.is_multicast or ip.is_unspecified or ip.is_link_local or ip.is_loopback:
        raise RouterConnectionError("Loopback, multicast and link-local addresses are not router targets.")
    if not any(ip in network for network in ranges):
        raise RouterConnectionError("Router IP is outside the administrator's allowed management networks.")
    return str(ip)


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RouterConnectionError("Router sent a redirect; refusing to forward login credentials.")


class MikroTikClient:
    def __init__(self, router, username, password, *, verify_tls=True):
        if router.family != "MIKROTIK":
            raise RouterConnectionError("This pilot connects to MikroTik RouterOS v7 only.")
        self.ip = require_allowed_router_ip(router.address)
        self.port = router.management_port
        if not (1 <= self.port <= 65535):
            raise RouterConnectionError("Invalid HTTPS management port.")
        if not username.strip() or not password:
            raise RouterConnectionError("Enter a dedicated RouterOS username and password.")
        if ":" in username or "\r" in username or "\n" in username:
            raise RouterConnectionError("Invalid RouterOS username.")
        if not verify_tls and not settings.DEBUG:
            raise RouterConnectionError("TLS certificate verification cannot be disabled in production.")
        ip_for_url = f"[{self.ip}]" if ":" in self.ip else self.ip
        self.base = f"https://{ip_for_url}:{self.port}/rest/"
        auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        self.authorization = f"Basic {auth}"
        if verify_tls:
            context = ssl.create_default_context(cafile=settings.MIKROTIK_CA_FILE or None)
        else:
            context = ssl._create_unverified_context()  # Debug-only pilot, explicit user opt-in.
        # No system proxy and no redirects: never send router credentials off target.
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), _NoRedirects())

    def _request(self, path, method="GET", payload=None):
        if path not in ("system/resource", "ip/hotspot", "ip/hotspot/user",
                        "ip/hotspot/user/profile", "ip/hotspot/active"):
            raise RouterConnectionError("Unsupported router operation.")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self.base + path, data=data, method=method,
            headers={
                "Authorization": self.authorization,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=7) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise RouterConnectionError("Router returned too much data. Contact WorldLink support.")
            return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 401:
                message = "RouterOS rejected the username/password."
            elif exc.code == 403:
                message = "RouterOS user does not have the required access."
            elif exc.code == 404:
                message = "RouterOS REST API was not found. RouterOS v7 with www-ssl is required."
            else:
                message = f"Router returned HTTP {exc.code}. Check its REST service and permissions."
            raise RouterConnectionError(message) from None
        except (URLError, OSError, socket.timeout, TimeoutError) as exc:
            if isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError) or isinstance(exc, ssl.SSLCertVerificationError):
                message = "TLS certificate is not trusted. Install its CA certificate on the server."
            else:
                message = "Cannot reach the router. Check its IP, VPN/LAN route and HTTPS management port."
            raise RouterConnectionError(message) from None
        except (UnicodeError, ValueError):
            raise RouterConnectionError("Router did not return valid RouterOS REST JSON.") from None

    def check_ready(self):
        info = self._request("system/resource")
        # RouterOS REST returns either a single object or a one-item list,
        # depending on the endpoint/router release.
        if isinstance(info, list) and len(info) == 1:
            info = info[0]
        if not isinstance(info, dict):
            raise RouterConnectionError("Router identification response was invalid.")
        version = str(info.get("version", ""))
        if not version.startswith("7."):
            raise RouterConnectionError("This pilot requires MikroTik RouterOS v7.")
        servers = self._request("ip/hotspot")
        if not isinstance(servers, list) or not any(
            row.get("disabled") not in ("true", True) for row in servers
        ):
            raise RouterConnectionError(
                "No enabled MikroTik HotSpot server found. Set up HotSpot on the guest bridge first."
            )
        return {
            "model": str(info.get("board-name", "MikroTik"))[:70],
            "version": version[:40],
        }

    @staticmethod
    def _marked_record(items, name, expected_marker):
        row = next((item for item in items if item.get("name") == name), None)
        if row is not None and row.get("comment") != expected_marker:
            raise RouterConnectionError(
                f"Router already has a different account/profile named {name}. "
                "No existing router records were overwritten."
            )
        return row

    def active_users(self):
        """A live, read-only RouterOS snapshot; never silently invent online sessions."""
        rows = self._request("ip/hotspot/active")
        if not isinstance(rows, list):
            raise RouterConnectionError("Router did not return a HotSpot Active list.")
        return [
            {
                "username": str(item.get("user") or "—")[:70],
                "address": str(item.get("address") or "—")[:70],
                "uptime": str(item.get("uptime") or "—")[:70],
            }
            for item in rows[:60]
        ], len(rows)

    def sync_sold_vouchers(self, router, actor, *, max_count=20):
        """Provision at most max_count cleared *manual sales* idempotently."""
        from .models import RouterVoucherSync
        from vouchers.models import Voucher

        vouchers = list(
            Voucher.objects.filter(
                company=router.company, status=Voucher.Status.SOLD, manual_sale__isnull=False
            ).exclude(router_syncs__router=router)
            .select_related("batch__plan")
            .order_by("pk")[:max_count]
        )
        if not vouchers:
            return 0

        profiles = self._request("ip/hotspot/user/profile")
        users = self._request("ip/hotspot/user")
        if not isinstance(profiles, list) or not isinstance(users, list):
            raise RouterConnectionError("Router HotSpot account list was not readable.")
        synced = 0
        for voucher in vouchers:
            plan = voucher.batch.plan
            profile_name = f"WHC-P{plan.pk}"
            profile_marker = f"WorldLink|plan|{plan.pk}"
            if not self._marked_record(profiles, profile_name, profile_marker):
                self._request("ip/hotspot/user/profile", "PUT", {
                    "name": profile_name,
                    "comment": profile_marker,
                    "shared-users": str(plan.device_limit),
                    # RouterOS rate-limit is router Rx (client upload) / Tx (client download).
                    "rate-limit": f"{plan.upload_kbps}k/{plan.download_kbps}k",
                })
                profiles.append({"name": profile_name, "comment": profile_marker})

            marker = f"WorldLink|voucher|{voucher.pk}"
            if not self._marked_record(users, voucher.code, marker):
                body = {
                    "name": voucher.code,
                    "password": voucher.code,
                    "profile": profile_name,
                    "limit-uptime": f"{plan.duration_minutes * 60}s",
                    "comment": marker,
                    "disabled": "false",
                }
                if plan.data_limit_mb:
                    body["limit-bytes-total"] = str(plan.data_limit_mb * 1024 * 1024)
                self._request("ip/hotspot/user", "PUT", body)
                users.append({"name": voucher.code, "comment": marker})

            # Write only after RouterOS confirms the user exists. The unique
            # constraint makes retries safe even if a previous HTTP response
            # succeeded before the database row could be committed.
            _, created = RouterVoucherSync.objects.get_or_create(
                router=router, voucher=voucher,
                defaults={"synced_by": actor},
            )
            synced += int(created)
        return synced
