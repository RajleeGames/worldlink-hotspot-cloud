"""Non-hardware safety checks for the first RouterOS connection pilot."""
import ipaddress
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from tenants.models import Company, Membership
from vouchers.models import Voucher, VoucherBatch, ManualSale
from .mikrotik import MikroTikClient, RouterConnectionError
from .models import Location, OmadaOnboarding, Router, RouterVoucherSync, WifiPlan

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


class OmadaOnboardingTests(TestCase):
    """Multiple tenants can submit metadata, but cannot enable live connectivity."""

    def setUp(self):
        self.company = Company.objects.create(name='Omada Customer')
        self.other_company = Company.objects.create(name='Other Omada Customer')
        self.owner = User.objects.create_user(username='omada-owner@example.com', password='a-test-password')
        self.other = User.objects.create_user(username='other-owner@example.com', password='a-test-password')
        self.staff = User.objects.create_superuser(username='platform-admin@example.com', password='a-test-password')
        Membership.objects.create(user=self.owner, company=self.company, role='OWNER')
        Membership.objects.create(user=self.other, company=self.other_company, role='OWNER')
        self.router = Router.objects.create(
            company=self.company,
            location=Location.objects.create(company=self.company, name='Site A'),
            name='Omada EAP', family=Router.Family.OMADA,
        )
        self.url = reverse('networks:omada_onboarding', args=[self.router.pk])

    def vpn_payload(self, **changes):
        data = {
            'action': 'submit', 'connection_mode': 'VPN',
            'controller_origin': 'https://my-controller.tail123.ts.net/',
            'controller_id': 'testControllerId0123456789abcdefgh',
            'ap_mac': 'b8:fb:b3:79:b5:60', 'ssid_name': 'GUEST-WIFI', 'setup_notes': '',
        }
        data.update(changes)
        return data

    def test_https_same_origin_form_post_passes_csrf_without_origin_header(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        page = browser.get(self.url, secure=True)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers['Referrer-Policy'], 'same-origin')
        self.assertIn('csrftoken', page.cookies)
        payload = self.vpn_payload()
        payload['csrfmiddlewaretoken'] = page.cookies['csrftoken'].value
        result = browser.post(self.url, payload, secure=True,
                              HTTP_REFERER='https://testserver' + self.url)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(OmadaOnboarding.objects.get(router=self.router).status,
                         OmadaOnboarding.Status.SUBMITTED)
        # A missing Origin and Referer must still be rejected over HTTPS.
        denied = browser.post(self.url, payload, secure=True)
        self.assertEqual(denied.status_code, 403)

    def test_new_omada_router_can_request_review_without_credentials(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(OmadaOnboarding.objects.count(), 0)  # GET never mutates DB
        response = self.client.post(self.url, self.vpn_payload())
        self.assertRedirects(response, self.url)
        profile = OmadaOnboarding.objects.get(router=self.router)
        self.assertEqual(profile.status, OmadaOnboarding.Status.SUBMITTED)
        self.assertIsNotNone(profile.submitted_at)
        self.assertEqual(profile.ap_mac, 'B8-FB-B3-79-B5-60')
        self.assertEqual(profile.controller_origin, 'https://my-controller.tail123.ts.net')
        self.assertNotIn('password', [f.name for f in profile._meta.fields])
        self.assertNotIn('api_key', [f.name for f in profile._meta.fields])
        self.assertContains(self.client.get(reverse('networks:routers')), 'Awaiting WorldLink review')

    def test_assisted_customer_can_send_details_without_private_vpn_yet(self):
        self.client.force_login(self.owner)
        data = self.vpn_payload(connection_mode='ASSISTED', controller_origin='', controller_id='',
                                ap_mac='', ssid_name='', setup_notes='Need help getting a private VPN.')
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(OmadaOnboarding.objects.get(router=self.router).status, OmadaOnboarding.Status.SUBMITTED)

    def test_save_draft_does_not_request_connection(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, {
            'action': 'save', 'connection_mode': 'ASSISTED', 'controller_origin': '',
            'controller_id': '', 'ap_mac': '', 'ssid_name': '', 'setup_notes': '',
        })
        self.assertRedirects(response, self.url)
        self.assertEqual(OmadaOnboarding.objects.get(router=self.router).status, OmadaOnboarding.Status.DRAFT)

    def test_origin_and_mac_input_are_validated_and_status_cannot_be_forged(self):
        self.client.force_login(self.owner)
        for url in ('http://my-controller.ts.net', 'https://user:pass@my-controller.ts.net',
                    'https://my-controller.ts.net/hotspot.html', 'https://my-controller.ts.net/?token=secret'):
            response = self.client.post(self.url, self.vpn_payload(controller_origin=url))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Enter an HTTPS origin only')
        for url in ('https://localhost:8043', 'https://127.0.0.1:8043'):
            response = self.client.post(self.url, self.vpn_payload(controller_origin=url))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'controller address')
        response = self.client.post(self.url, self.vpn_payload(ap_mac='bad-mac'))
        self.assertContains(response, 'Enter a valid AP MAC')
        response = self.client.post(self.url, self.vpn_payload(setup_notes='password=oops'))
        self.assertContains(response, 'Remove credentials or tokens')
        self.assertFalse(OmadaOnboarding.objects.exists())
        self.assertRedirects(
            self.client.post(self.url, self.vpn_payload(status='REVIEWED', reviewed_by=self.staff.pk)),
            self.url,
        )
        self.assertEqual(OmadaOnboarding.objects.get().status, OmadaOnboarding.Status.SUBMITTED)

    def test_customer_dashboard_shows_own_router_and_setup_state_not_another_company(self):
        second = Router.objects.create(
            company=self.other_company,
            location=Location.objects.create(company=self.other_company, name='Remote location'),
            name='SECRET-OTHER-TENANT-ROUTER', family=Router.Family.OMADA,
        )
        OmadaOnboarding.objects.create(
            router=second, status=OmadaOnboarding.Status.REVIEWED,
            controller_id='should-not-display-other-tenant-id',
        )
        self.client.force_login(self.owner)
        dashboard_url = reverse('cloud:dashboard')
        response = self.client.get(dashboard_url)
        self.assertContains(response, 'Omada EAP')
        self.assertContains(response, 'Added · setup needed')
        self.assertNotContains(response, 'SECRET-OTHER-TENANT-ROUTER')
        self.assertNotContains(response, 'should-not-display-other-tenant-id')
        self.client.post(self.url, self.vpn_payload())
        response = self.client.get(dashboard_url)
        self.assertContains(response, 'Awaiting WorldLink review')
        self.assertContains(response, 'testControllerId0123456789abcdefgh')
        self.assertContains(response, '1 Omada access points registered')
        self.assertContains(response, '1 awaiting review')

    def test_tenant_isolation_viewer_denial_and_mikrotik_exclusion(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.vpn_payload()).status_code, 404)
        self.assertFalse(OmadaOnboarding.objects.exists())
        self.client.force_login(self.owner)
        Membership.objects.filter(user=self.owner).update(role='VIEWER')
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.vpn_payload()).status_code, 403)
        Membership.objects.filter(user=self.owner).update(role='OWNER')
        mikrotik = Router.objects.create(company=self.company, location=self.router.location,
                                        name='Other model', family=Router.Family.MIKROTIK)
        self.assertEqual(self.client.get(reverse('networks:omada_onboarding', args=[mikrotik.pk])).status_code, 404)

    def test_staff_review_and_resubmission_do_not_activate_live_service(self):
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(self.url, self.vpn_payload()), self.url)
        profile = OmadaOnboarding.objects.get(router=self.router)
        review_url = reverse('controlcenter:review_router_onboarding', args=[profile.pk])
        self.assertEqual(self.client.get(reverse('controlcenter:router_onboardings')).status_code, 403)
        self.assertEqual(self.client.post(review_url, {'decision': 'reviewed'}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse('controlcenter:router_onboardings')), 'Omada Customer')
        self.assertEqual(self.client.get(review_url).status_code, 405)
        self.assertRedirects(self.client.post(review_url, {'decision': 'needs_info', 'note': 'Need VPN details.'}),
                             reverse('controlcenter:router_onboardings'))
        profile.refresh_from_db()
        self.assertEqual(profile.status, OmadaOnboarding.Status.NEEDS_INFO)
        self.assertEqual(profile.review_note, 'Need VPN details.')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(self.url), 'Need VPN details.')
        self.assertRedirects(self.client.post(self.url, self.vpn_payload()), self.url)
        profile.refresh_from_db()
        self.assertEqual(profile.status, OmadaOnboarding.Status.SUBMITTED)
        self.assertEqual(profile.review_note, '')
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.post(review_url, {'decision': 'reviewed'}),
                             reverse('controlcenter:router_onboardings'))
        profile.refresh_from_db()
        self.assertEqual(profile.status, OmadaOnboarding.Status.REVIEWED)
        self.assertIsNone(self.router.last_checked_at)
        self.assertEqual(RouterVoucherSync.objects.count(), 0)

    def test_staff_does_not_approve_drafts_or_accept_unbounded_notes(self):
        self.client.force_login(self.owner)
        self.client.post(self.url, self.vpn_payload(action='save'))
        profile = OmadaOnboarding.objects.get(router=self.router)
        review_url = reverse('controlcenter:review_router_onboarding', args=[profile.pk])
        self.client.force_login(self.staff)
        self.client.post(review_url, {'decision': 'reviewed'})
        profile.refresh_from_db()
        self.assertEqual(profile.status, OmadaOnboarding.Status.DRAFT)
        self.client.force_login(self.owner)
        self.client.post(self.url, self.vpn_payload())
        self.client.force_login(self.staff)
        self.client.post(review_url, {'decision': 'needs_info', 'note': ''})
        self.client.post(review_url, {'decision': 'reviewed', 'note': 'x' * 401})
        profile.refresh_from_db()
        self.assertEqual(profile.status, OmadaOnboarding.Status.SUBMITTED)
