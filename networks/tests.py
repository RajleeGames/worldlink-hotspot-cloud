"""Non-hardware safety checks for the first RouterOS connection pilot."""
import ipaddress
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from tenants.models import Company, Membership
from vouchers.models import Voucher, VoucherBatch, ManualSale
from .mikrotik import MikroTikClient, RouterConnectionError
from .models import Location, Router, RouterVoucherSync, WifiPlan

User = get_user_model()
ALLOWED = (ipaddress.ip_network("192.168.88.1/32"),)


class RouterPilotTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="WorldLink Test Shop")
        self.other_company = Company.objects.create(name="Other Shop")
        self.owner = User.objects.create_user(username="pilot-owner@example.com", password="PilotPass!12345")
        self.other = User.objects.create_user(username="pilot-other@example.com", password="PilotPass!12345")
        Membership.objects.create(user=self.owner, company=self.company, role="OWNER")
        Membership.objects.create(user=self.other, company=self.other_company, role="OWNER")
        self.location = Location.objects.create(company=self.company, name="Main")
        self.router = Router.objects.create(
            company=self.company, location=self.location, name="Router A",
            address="192.168.88.1", management_port=443,
        )
        self.plan = WifiPlan.objects.create(
            company=self.company, name="Hour", duration_minutes=60, price=1000,
            download_kbps=5000, upload_kbps=1000, data_limit_mb=250, device_limit=2,
        )
        self.batch = VoucherBatch.objects.create(
            company=self.company, plan=self.plan, quantity=2, created_by=self.owner,
        )
        self.sold = Voucher.objects.create(company=self.company, batch=self.batch, code="WHC-PAID123456")
        self.ready = Voucher.objects.create(company=self.company, batch=self.batch, code="WHC-UNPAID1234")
        self.sold.status = Voucher.Status.SOLD
        self.sold.save(update_fields=["status"])
        ManualSale.objects.create(
            company=self.company, voucher=self.sold, amount=1000,
            method=ManualSale.PaymentMethod.CASH, recorded_by=self.owner,
        )

    @staticmethod
    def fake_api():
        profiles, users, posts = [], [], []

        def handle(path, method="GET", payload=None):
            if path == "system/resource":
                return [{"board-name": "hAP ax2", "version": "7.20.2"}]
            if path == "ip/hotspot":
                return [{"name": "hotspot1", "disabled": "false"}]
            if path == "ip/hotspot/active":
                return [{"user": "WHC-PAID123456", "address": "10.5.50.100", "uptime": "5m22s"}]
            if path == "ip/hotspot/user/profile":
                if method == "GET":
                    return list(profiles)
                profiles.append(payload)
                posts.append(("profile", payload))
                return {"ret": "*1"}
            if path == "ip/hotspot/user":
                if method == "GET":
                    return list(users)
                users.append(payload)
                posts.append(("user", payload))
                return {"ret": "*2"}
            raise AssertionError(f"Unexpected router REST operation: {path}")

        return handle, posts

    @override_settings(MIKROTIK_ALLOWED_CIDRS=ALLOWED)
    def test_test_button_is_read_only_and_no_router_password_persisted(self):
        fake, posts = self.fake_api()
        self.client.force_login(self.owner)
        with patch.object(MikroTikClient, "_request", side_effect=fake):
            result = self.client.post(
                reverse("networks:router_connect", args=[self.router.pk]),
                {"username": "worldlink", "password": "very-private-router-secret",
                 "verify_tls": "on", "action": "test"},
            )
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "RouterOS HTTPS connection successful")
        self.assertNotContains(result, "very-private-router-secret")
        self.assertEqual(posts, [])
        self.router.refresh_from_db()
        self.assertIsNotNone(self.router.last_checked_at)
        self.assertEqual(RouterVoucherSync.objects.count(), 0)

    @override_settings(MIKROTIK_ALLOWED_CIDRS=ALLOWED)
    def test_only_confirmed_manual_sale_syncs_and_sync_is_idempotent(self):
        fake, posts = self.fake_api()
        self.client.force_login(self.owner)
        url = reverse("networks:router_connect", args=[self.router.pk])
        data = {"username": "worldlink", "password": "secret", "verify_tls": "on", "action": "sync"}
        with patch.object(MikroTikClient, "_request", side_effect=fake):
            response = self.client.post(url, data)
            again = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(RouterVoucherSync.objects.count(), 1)
        self.assertEqual(len(posts), 2)
        profile = next(item for kind, item in posts if kind == "profile")
        user = next(item for kind, item in posts if kind == "user")
        self.assertEqual(profile["rate-limit"], "1000k/5000k")
        self.assertEqual(profile["shared-users"], "2")
        self.assertEqual(user["name"], self.sold.code)
        self.assertEqual(user["password"], self.sold.code)
        self.assertEqual(user["limit-uptime"], "3600s")
        self.assertEqual(user["limit-bytes-total"], str(250 * 1024 * 1024))
        self.assertNotEqual(user["name"], self.ready.code)

    @override_settings(MIKROTIK_ALLOWED_CIDRS=ALLOWED)
    def test_router_existing_unrelated_name_is_never_overwritten(self):
        fake, posts = self.fake_api()

        def conflicting(path, method="GET", payload=None):
            if path == "ip/hotspot/user":
                return [{"name": self.sold.code, "comment": "Local guest"}]
            return fake(path, method, payload)

        self.client.force_login(self.owner)
        with patch.object(MikroTikClient, "_request", side_effect=conflicting):
            response = self.client.post(
                reverse("networks:router_connect", args=[self.router.pk]),
                {"username": "test", "password": "secret", "verify_tls": "on", "action": "sync"},
            )
        self.assertContains(response, "No existing router records were overwritten")
        self.assertEqual(RouterVoucherSync.objects.count(), 0)
        self.assertFalse(any(kind == "user" for kind, _ in posts))

    def test_tenant_isolation_and_roles(self):
        self.client.force_login(self.other)
        url = reverse("networks:router_connect", args=[self.router.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        Membership.objects.filter(user=self.owner).update(role="VIEWER")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"action": "test"}).status_code, 403)

    @override_settings(MIKROTIK_ALLOWED_CIDRS=ALLOWED)
    def test_live_active_view_reads_router_but_does_not_write_sessions(self):
        from hotspots.models import HotspotSession
        fake, posts = self.fake_api()
        self.client.force_login(self.owner)
        with patch.object(MikroTikClient, "_request", side_effect=fake):
            result = self.client.post(
                reverse("networks:router_connect", args=[self.router.pk]),
                {"username": "worldlink", "password": "secret", "verify_tls": "on", "action": "online"},
            )
        self.assertContains(result, "10.5.50.100")
        self.assertContains(result, "5m22s")
        self.assertEqual(posts, [])
        self.assertEqual(HotspotSession.objects.count(), 0)

    def test_first_router_onboarding_creates_main_site_only_on_save(self):
        new_company = Company.objects.create(name="Brand New Internet Shop")
        fresh_owner = User.objects.create_user(username="fresh-owner@example.com", password="PilotPass!12345")
        Membership.objects.create(user=fresh_owner, company=new_company, role="OWNER")
        self.client.force_login(fresh_owner)
        self.assertEqual(Location.objects.filter(company=new_company).count(), 0)
        self.assertEqual(self.client.get(reverse("networks:router_new")).status_code, 200)
        self.assertEqual(Location.objects.filter(company=new_company).count(), 0)
        response = self.client.post(reverse("networks:router_new"), {
            "name": "First Router", "location": "", "family": "MIKROTIK",
            "model_name": "hEX S", "address": "192.168.88.1",
            "management_port": "443", "serial": "", "notes": "",
        })
        self.assertEqual(response.status_code, 302)
        new_router = Router.objects.get(company=new_company)
        self.assertEqual(new_router.location.name, "Main site")
        self.assertEqual(Location.objects.filter(company=new_company).count(), 1)

    @override_settings(MIKROTIK_ALLOWED_CIDRS=())
    def test_no_connection_without_administrator_allowlist(self):
        with self.assertRaisesRegex(RouterConnectionError, "disabled"):
            MikroTikClient(self.router, "username", "password")

    @override_settings(MIKROTIK_ALLOWED_CIDRS=ALLOWED, DEBUG=False)
    def test_no_unverified_tls_in_production(self):
        with self.assertRaisesRegex(RouterConnectionError, "production"):
            MikroTikClient(self.router, "username", "password", verify_tls=False)

    @override_settings(MIKROTIK_ALLOWED_CIDRS=ALLOWED)
    def test_no_sync_without_hotspot_server(self):
        fake, posts = self.fake_api()

        def no_hotspot(path, method="GET", payload=None):
            if path == "ip/hotspot":
                return []
            return fake(path, method, payload)

        self.client.force_login(self.owner)
        with patch.object(MikroTikClient, "_request", side_effect=no_hotspot):
            response = self.client.post(
                reverse("networks:router_connect", args=[self.router.pk]),
                {"username": "worldlink", "password": "secret", "verify_tls": "on", "action": "sync"},
            )
        self.assertContains(response, "No enabled MikroTik HotSpot server")
        self.assertEqual(posts, [])
        self.assertEqual(RouterVoucherSync.objects.count(), 0)
