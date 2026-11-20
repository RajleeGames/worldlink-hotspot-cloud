"""No-hardware tests: read-only Omada observation never authorizes Wi-Fi."""

import io
import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tenants.models import Company, Membership
from .models import Location, OmadaDeviceObservation, OmadaOnboarding, Router
from .omada_monitor import OmadaMonitorError, OmadaReadOnlyClient, poll_approved_pilot


PILOT = {
    'OMADA_LIVE_ENABLED': True,
    'OMADA_PILOT_COMPANY_ID': 1,
    'OMADA_CONTROLLER_URL': 'https://pilot.tailtest.ts.net',
    'OMADA_CONTROLLER_ID': 'controllerId1234567890abcdefgh',
    'OMADA_AP_MAC': 'B8-FB-B3-79-B5-60',
    'OMADA_SSID': 'WORLDLINK-PAY',
    'OMADA_OPENAPI_CLIENT_ID': 'view-only-client',
    'OMADA_OPENAPI_CLIENT_SECRET': 'super-private-monitor-secret',
    'OMADA_OPENAPI_API_KEY': '',
    'OMADA_OPENAPI_SITE_ID': '',
    'OMADA_CA_FILE': '',
}


class FakeOmadaOpener:
    """Reject any request besides token acquisition and listing sites/devices."""

    def __init__(self, *, status='CONNECTED', sites=None, devices=None):
        self.requests = []
        self.status = status
        self.sites = sites if sites is not None else [{'siteId': 'siteA', 'name': 'Pilot'}]
        self.devices = devices

    def open(self, request, timeout=None):
        url = request.full_url
        self.requests.append((request.get_method(), url, request.get_header('Authorization'), request.data))
        assert timeout == 12
        assert url.startswith('https://pilot.tailtest.ts.net/')
        path = urlsplit(url).path
        if path == '/openapi/authorize/token':
            assert request.get_method() == 'POST'
            assert 'client_secret' in json.loads(request.data)
            body = {'errorCode': 0, 'result': {'accessToken': 'AT-test-only'}}
        elif path.endswith('/sites'):
            assert request.get_method() == 'GET'
            assert request.get_header('Authorization') in ('AccessToken=AT-test-only', 'Bearer AK-fake-view-only')
            body = {'errorCode': 0, 'result': {'data': self.sites}}
        elif path.endswith('/sites/siteA/devices'):
            assert request.get_method() == 'GET'
            assert request.get_header('Authorization') in ('AccessToken=AT-test-only', 'Bearer AK-fake-view-only')
            device_list = self.devices if self.devices is not None else [
                {'mac': 'B8-FB-B3-79-B5-60', 'status': self.status},
            ]
            body = {'errorCode': 0, 'result': {'data': device_list}}
        else:
            raise AssertionError('Unexpected Omada API call: ' + path)
        return io.BytesIO(json.dumps(body).encode('utf-8'))


@override_settings(**PILOT)
class OmadaMonitorTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Eaglelink demo')
        self.other_company = Company.objects.create(name='Unrelated tenant')
        self.owner = get_user_model().objects.create_user(username='omada-pilot-owner', password='not-in-database')
        self.other = get_user_model().objects.create_user(username='omada-other-owner', password='not-in-database')
        self.staff = get_user_model().objects.create_user(username='omada-staff', password='not-in-database')
        Membership.objects.create(company=self.company, user=self.owner, role='OWNER')
        Membership.objects.create(company=self.other_company, user=self.other, role='OWNER')
        self.router = Router.objects.create(
            company=self.company, location=Location.objects.create(company=self.company, name='Main'),
            family=Router.Family.OMADA, name='Eaglelink EAP225',
        )
        self.profile = OmadaOnboarding.objects.create(
            router=self.router, connection_mode=OmadaOnboarding.ConnectionMode.VPN,
            controller_origin=PILOT['OMADA_CONTROLLER_URL'], controller_id=PILOT['OMADA_CONTROLLER_ID'],
            ap_mac=PILOT['OMADA_AP_MAC'], ssid_name=PILOT['OMADA_SSID'],
            status=OmadaOnboarding.Status.REVIEWED, reviewed_by=self.staff,
        )
        self.other_router = Router.objects.create(
            company=self.other_company, location=Location.objects.create(company=self.other_company, name='Remote'),
            family=Router.Family.OMADA, name='PRIVATE-OTHER-ROUTER',
        )
        OmadaOnboarding.objects.create(
            router=self.other_router, connection_mode=OmadaOnboarding.ConnectionMode.VPN,
            controller_origin='https://other.tailtest.ts.net', controller_id='otherTenantController1234567890',
            ap_mac=PILOT['OMADA_AP_MAC'], ssid_name=PILOT['OMADA_SSID'],
            status=OmadaOnboarding.Status.REVIEWED, reviewed_by=self.staff,
        )

    def test_authenticated_probe_is_read_only_and_scoped_to_reviewed_pilot(self):
        fake = FakeOmadaOpener()
        with patch('networks.omada_monitor.build_opener', return_value=fake) as builder:
            record = poll_approved_pilot()
        self.assertEqual(record.state, OmadaDeviceObservation.State.CONNECTED)
        self.assertTrue(record.is_fresh)
        self.assertEqual(record.router_id, self.router.id)
        self.assertEqual(OmadaDeviceObservation.objects.count(), 1)
        self.assertFalse(OmadaDeviceObservation.objects.filter(router=self.other_router).exists())
        self.assertEqual([method for method, _, _, _ in fake.requests], ['POST', 'GET', 'GET'])
        self.assertEqual([arg.__class__.__name__ for arg in builder.call_args.args], ['ProxyHandler', 'HTTPSHandler', '_NoRedirect'])
        for method, url, _, _ in fake.requests:
            self.assertNotIn(self.other_router.name, url)
        self.assertNotIn('super-private-monitor-secret', record.reported_status)

    def test_unknown_numeric_status_does_not_claim_ap_is_online(self):
        fake = FakeOmadaOpener(status=1)
        with patch('networks.omada_monitor.build_opener', return_value=fake):
            record = poll_approved_pilot()
        self.assertEqual(record.state, OmadaDeviceObservation.State.UNKNOWN)
        self.assertEqual(record.reported_status, '1')
        self.client.force_login(self.owner)
        page = self.client.get(reverse('networks:routers'))
        self.assertContains(page, 'Status not recognized')
        self.assertNotContains(page, '<span class="pill ready">Connected</span>')

    def test_offline_and_missing_ap_are_not_online(self):
        for fake, expected in (
            (FakeOmadaOpener(status='Disconnected'), OmadaDeviceObservation.State.OFFLINE),
            (FakeOmadaOpener(devices=[]), OmadaDeviceObservation.State.NOT_FOUND),
        ):
            with self.subTest(expected=expected), patch('networks.omada_monitor.build_opener', return_value=fake):
                self.assertEqual(poll_approved_pilot().state, expected)

    def test_stale_observation_and_resubmission_remove_connected_badge(self):
        obs = OmadaDeviceObservation.objects.create(
            router=self.router, state=OmadaDeviceObservation.State.CONNECTED,
            checked_at=timezone.now() - timedelta(minutes=5),
        )
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('networks:routers')), 'AP not recently verified')
        obs.checked_at = timezone.now()
        obs.save(update_fields=['checked_at'])
        self.assertContains(self.client.get(reverse('networks:routers')), 'Connected')
        self.profile.status = OmadaOnboarding.Status.SUBMITTED
        self.profile.save(update_fields=['status'])
        self.assertFalse(obs.is_fresh)
        self.assertContains(self.client.get(reverse('networks:routers')), 'AP not recently verified')

    def test_other_tenant_never_sees_pilot_status_or_details(self):
        OmadaDeviceObservation.objects.create(
            router=self.router, state=OmadaDeviceObservation.State.CONNECTED, checked_at=timezone.now(),
        )
        self.client.force_login(self.other)
        for url in (reverse('networks:routers'), reverse('cloud:dashboard')):
            page = self.client.get(url)
            self.assertNotContains(page, 'Eaglelink EAP225')
            self.assertNotContains(page, 'controllerId1234567890abcdefgh')
            self.assertNotContains(page, 'Connected</strong>')

    def test_unreviewed_and_mismatched_pilot_never_calls_api(self):
        self.profile.status = OmadaOnboarding.Status.DRAFT
        self.profile.save(update_fields=['status'])
        with patch('networks.omada_monitor.build_opener') as opener:
            with self.assertRaises(OmadaMonitorError):
                poll_approved_pilot()
            opener.assert_not_called()
        self.profile.status = OmadaOnboarding.Status.REVIEWED
        self.profile.ssid_name = 'Someone-else-SSID'
        self.profile.save(update_fields=['status', 'ssid_name'])
        with patch('networks.omada_monitor.build_opener') as opener:
            with self.assertRaises(OmadaMonitorError):
                poll_approved_pilot()
            opener.assert_not_called()

    def test_bad_auth_does_not_leave_old_online_check_fresh(self):
        OmadaDeviceObservation.objects.create(
            router=self.router, state=OmadaDeviceObservation.State.CONNECTED, checked_at=timezone.now(),
        )
        with override_settings(OMADA_OPENAPI_CLIENT_SECRET=''), self.assertRaises(OmadaMonitorError):
            poll_approved_pilot()
        obs = OmadaDeviceObservation.objects.get(router=self.router)
        self.assertEqual(obs.state, OmadaDeviceObservation.State.ERROR)

    def test_site_selection_enforces_one_visible_site_unless_explicitly_pinned(self):
        fake = FakeOmadaOpener(sites=[{'siteId': 'siteA'}, {'siteId': 'siteB'}])
        with patch('networks.omada_monitor.build_opener', return_value=fake):
            with self.assertRaisesMessage(OmadaMonitorError, 'OMADA_OPENAPI_SITE_ID'):
                poll_approved_pilot()
        with override_settings(OMADA_OPENAPI_SITE_ID='siteA'), patch(
            'networks.omada_monitor.build_opener', return_value=FakeOmadaOpener(sites=[{'siteId': 'siteA'}, {'siteId': 'siteB'}]),
        ):
            self.assertEqual(poll_approved_pilot().state, OmadaDeviceObservation.State.CONNECTED)

    def test_api_key_mode_gets_only_read_endpoint(self):
        key = 'AK-fake-view-only'
        fake = FakeOmadaOpener()
        with override_settings(OMADA_OPENAPI_CLIENT_ID='', OMADA_OPENAPI_CLIENT_SECRET='', OMADA_OPENAPI_API_KEY=key):
            with patch('networks.omada_monitor.build_opener', return_value=fake):
                record = poll_approved_pilot()
        self.assertEqual(record.state, OmadaDeviceObservation.State.CONNECTED)
        self.assertEqual([method for method, _, _, _ in fake.requests], ['GET', 'GET'])

    def test_manual_command_reports_without_a_real_controller(self):
        fake = FakeOmadaOpener()
        with patch('networks.omada_monitor.build_opener', return_value=fake):
            out = io.StringIO()
            call_command('poll_omada_pilot', stdout=out)
        self.assertIn('Connected', out.getvalue())
        self.assertNotIn('super-private-monitor-secret', out.getvalue())
        with self.assertRaises(CommandError):
            call_command('poll_omada_pilot', interval=1, stdout=io.StringIO())
