"""Multi-tenant central Omada intake and read-only status, without hardware."""

import io
import json
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from payments.collections import collection_enabled_for
from tenants.models import Company, Membership
from .models import Location, OmadaDeviceObservation, OmadaManagedSite, OmadaOnboarding, Router
from .omada_monitor import poll_approved_managed


MANAGED = {
    'OMADA_CONTROLLER_URL': 'https://omada.worldlinksecurity.co.tz',
    'OMADA_CONTROLLER_ID': 'controllerId1234567890abcdefgh',
    'OMADA_CENTRAL_INFORM_HOST': 'omada.worldlinksecurity.co.tz',
    'OMADA_OPENAPI_CLIENT_ID': 'staff-view-only',
    'OMADA_OPENAPI_CLIENT_SECRET': 'fake-read-only-secret',
    'OMADA_OPENAPI_API_KEY': '',
    'OMADA_OPENAPI_SITE_ID': '',
    'OMADA_CA_FILE': '',
    'EVPAY_COLLECTION_COMPANY_IDS': (1,),
    'OMADA_PILOT_COMPANY_ID': 1,
}


class ReadOnlyMultiSiteOmada:
    def __init__(self, *, first_status=1, second_status=1, sites=None):
        self.calls = []
        self.first_status, self.second_status = first_status, second_status
        self.sites = sites if sites is not None else [
            {'siteId': 'apiSiteA', 'name': 'Alpha site'},
            {'siteId': 'apiSiteB', 'name': 'Beta site'},
        ]

    def open(self, request, timeout=None):
        path = urlsplit(request.full_url).path
        self.calls.append((request.get_method(), path))
        assert timeout == 12
        assert request.full_url.startswith('https://omada.worldlinksecurity.co.tz/')
        if path == '/openapi/authorize/token':
            assert request.get_method() == 'POST'
            body = {'errorCode': 0, 'result': {'accessToken': 'fake-token'}}
        elif path.endswith('/sites'):
            assert request.get_method() == 'GET'
            body = {'errorCode': 0, 'result': {'data': self.sites}}
        elif path.endswith('/sites/apiSiteA/devices'):
            assert request.get_method() == 'GET'
            body = {'errorCode': 0, 'result': {'data': [
                {'mac': 'AA-BB-CC-11-22-33', 'status': self.first_status},
            ]}}
        elif path.endswith('/sites/apiSiteB/devices'):
            assert request.get_method() == 'GET'
            body = {'errorCode': 0, 'result': {'data': [
                {'mac': 'AA-BB-CC-44-55-66', 'status': self.second_status},
            ]}}
        elif path.endswith('/clients'):
            assert request.get_method() == 'GET'
            body = {'errorCode': 0, 'result': {'data': [], 'totalRows': 0}}
        else:
            raise AssertionError('Unknown Omada endpoint ' + path)
        return io.BytesIO(json.dumps(body).encode())


@override_settings(**MANAGED)
class CentralOmadaBusinessTests(TestCase):
    def setUp(self):
        self.alpha = Company.objects.create(name='Alpha hotspot')
        self.beta = Company.objects.create(name='Beta hotspot')
        self.owner_a = get_user_model().objects.create_user(username='alpha-owner@test.example', password='pass')
        self.owner_b = get_user_model().objects.create_user(username='beta-owner@test.example', password='pass')
        self.staff = get_user_model().objects.create_superuser(username='platform-admin@test.example', password='pass')
        Membership.objects.create(company=self.alpha, user=self.owner_a, role='OWNER')
        Membership.objects.create(company=self.beta, user=self.owner_b, role='OWNER')
        self.ap_a = Router.objects.create(
            company=self.alpha, location=Location.objects.create(company=self.alpha, name='Shop 1'),
            name='Alpha EAP225', family=Router.Family.OMADA, serial='EAP-A',
        )
        self.ap_b = Router.objects.create(
            company=self.beta, location=Location.objects.create(company=self.beta, name='Shop 2'),
            name='Beta EAP225', family=Router.Family.OMADA, serial='EAP-B',
        )

    @staticmethod
    def details(mac):
        return {
            'action': 'submit', 'connection_mode': 'CENTRAL',
            'controller_origin': '', 'controller_id': '',
            'ap_mac': mac, 'ssid_name': 'GUEST-PAY',
            'setup_notes': 'Outdoor EAP, wired internet uplink.',
        }

    @staticmethod
    def assignment(site, api):
        return {'decision': 'reviewed', 'site_name': site,
                'inform_site_id': 'abcdef0123456789' + ('aa' if site == 'Alpha site' else 'bb'),
                'openapi_site_id': api}

    def submit(self, user, router, mac):
        self.client.force_login(user)
        url = reverse('networks:omada_onboarding', args=[router.pk])
        self.assertRedirects(self.client.post(url, self.details(mac)), url)
        return OmadaOnboarding.objects.get(router=router)

    def approve(self, profile, payload):
        self.client.force_login(self.staff)
        return self.client.post(reverse('controlcenter:review_router_onboarding', args=[profile.pk]), payload)

    def test_central_intake_needs_mac_and_ssid_and_never_accepts_site_ids_from_tenant(self):
        self.client.force_login(self.owner_a)
        url = reverse('networks:omada_onboarding', args=[self.ap_a.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Connect to WorldLink central Omada')
        self.assertContains(page, 'No router passwords or payment API keys are needed here.')
        self.assertEqual(page.headers['Referrer-Policy'], 'same-origin')
        self.assertContains(self.client.post(url, self.details('',)), 'Required to connect this AP')
        self.assertContains(self.client.post(url, self.details('AA:BB:CC:11:22:33') | {'ssid_name': ''}),
                            'Required to connect this AP')
        self.assertFalse(OmadaOnboarding.objects.exists())
        profile = self.submit(self.owner_a, self.ap_a, 'AA:BB:CC:11:22:33')
        self.assertEqual(profile.ap_mac, 'AA-BB-CC-11-22-33')
        self.assertEqual(profile.status, OmadaOnboarding.Status.SUBMITTED)
        self.assertIsNone(profile.managed_site)
        # A tenant may post extra fields, but cannot assign a central site.
        self.client.post(url, self.details('AA:BB:CC:11:22:33') | {'managed_site': 321, 'status': 'REVIEWED'})
        profile.refresh_from_db()
        self.assertIsNone(profile.managed_site)
        self.assertEqual(profile.status, OmadaOnboarding.Status.SUBMITTED)

    def test_new_business_can_add_router_with_model_and_serial_then_start_setup(self):
        newcomer = Company.objects.create(name='New signup without locations')
        new_owner = get_user_model().objects.create_user(username='newly-joined@test.example', password='pass')
        Membership.objects.create(company=newcomer, user=new_owner, role='OWNER')
        self.client.force_login(new_owner)
        url = reverse('networks:router_new')
        data = {
            'name': 'Branch access point', 'family': Router.Family.OMADA,
            'model_name': 'EAP225-Outdoor', 'serial': '', 'location': '',
            'address': '', 'management_port': '443', 'notes': '',
        }
        self.assertContains(self.client.post(url, data), 'Required for a remote Omada access point')
        data['serial'] = '1234567890ABC'
        result = self.client.post(url, data)
        router = Router.objects.get(company=newcomer, name='Branch access point')
        self.assertRedirects(result, reverse('networks:omada_onboarding', args=[router.pk]))
        self.assertEqual(router.location.name, 'Main site')

    def test_team_assigns_isolated_central_sites_without_enabling_paid_internet(self):
        a = self.submit(self.owner_a, self.ap_a, 'AA:BB:CC:11:22:33')
        b = self.submit(self.owner_b, self.ap_b, 'AA:BB:CC:44:55:66')
        review = reverse('controlcenter:review_router_onboarding', args=[a.pk])
        self.assertEqual(self.client.post(review, self.assignment('Alpha site', 'apiSiteA')).status_code, 403)
        self.assertRedirects(self.approve(a, {'decision': 'reviewed'}), reverse('controlcenter:router_onboardings'))
        a.refresh_from_db()
        self.assertEqual(a.status, OmadaOnboarding.Status.SUBMITTED)
        self.assertRedirects(self.approve(a, self.assignment('Alpha site', 'apiSiteA')),
                             reverse('controlcenter:router_onboardings'))
        self.assertRedirects(self.approve(b, self.assignment('Beta site', 'apiSiteB')),
                             reverse('controlcenter:router_onboardings'))
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(OmadaManagedSite.objects.count(), 2)
        self.assertNotEqual(a.managed_site_id, b.managed_site_id)
        self.assertEqual(a.managed_site.company_id, self.alpha.pk)
        self.assertEqual(b.managed_site.company_id, self.beta.pk)
        self.assertEqual(a.managed_site.inform_url,
                         'omada://omada.worldlinksecurity.co.tz?dPort=29810&mPort=29814&omadacId=abcdef0123456789aa')
        self.client.force_login(self.owner_a)
        page = self.client.get(reverse('networks:omada_onboarding', args=[self.ap_a.pk]))
        self.assertContains(page, 'Alpha site')
        self.assertContains(page, 'omada://omada.worldlinksecurity.co.tz')
        self.assertNotContains(page, 'Beta site')
        self.assertNotContains(page, 'abcdef0123456789bb')
        self.assertFalse(collection_enabled_for(self.beta))
        self.assertEqual(OmadaDeviceObservation.objects.count(), 0)

    def test_cannot_assign_one_site_or_one_ap_to_two_businesses(self):
        a = self.submit(self.owner_a, self.ap_a, 'AA:BB:CC:11:22:33')
        b = self.submit(self.owner_b, self.ap_b, 'AA:BB:CC:44:55:66')
        self.approve(a, self.assignment('Alpha site', 'apiSiteA'))
        self.approve(b, {'decision': 'reviewed', 'site_name': 'Imposter',
                         'inform_site_id': 'abcdef0123456789aa', 'openapi_site_id': 'apiSiteA'})
        b.refresh_from_db()
        self.assertEqual(b.status, OmadaOnboarding.Status.SUBMITTED)
        self.assertIsNone(b.managed_site_id)
        self.approve(b, {'decision': 'reviewed', 'site_name': 'Imposter',
                         'inform_site_id': 'abcdef0123456789bb', 'openapi_site_id': 'apiSiteA'})
        b.refresh_from_db()
        self.assertIsNone(b.managed_site_id)
        self.assertEqual(OmadaManagedSite.objects.count(), 1)
        self.client.force_login(self.owner_b)
        self.client.post(reverse('networks:omada_onboarding', args=[self.ap_b.pk]),
                         self.details('AA:BB:CC:11:22:33'))
        b.refresh_from_db()
        self.approve(b, self.assignment('Beta site', 'apiSiteB'))
        b.refresh_from_db()
        self.assertEqual(b.status, OmadaOnboarding.Status.SUBMITTED)

    def test_live_status_is_read_only_per_site_and_isolation_holds(self):
        a = self.submit(self.owner_a, self.ap_a, 'AA:BB:CC:11:22:33')
        b = self.submit(self.owner_b, self.ap_b, 'AA:BB:CC:44:55:66')
        self.approve(a, self.assignment('Alpha site', 'apiSiteA'))
        self.approve(b, self.assignment('Beta site', 'apiSiteB'))
        fake = ReadOnlyMultiSiteOmada(second_status=0)
        with patch('networks.omada_monitor.build_opener', return_value=fake):
            observations = poll_approved_managed()
        self.assertEqual(len(observations), 2)
        self.assertEqual(OmadaDeviceObservation.objects.get(router=self.ap_a).state, 'CONNECTED')
        self.assertEqual(OmadaDeviceObservation.objects.get(router=self.ap_b).state, 'OFFLINE')
        self.assertTrue(OmadaDeviceObservation.objects.get(router=self.ap_a).is_fresh)
        self.assertTrue(OmadaDeviceObservation.objects.get(router=self.ap_b).is_fresh)
        self.assertTrue(all(method == 'GET' or path == '/openapi/authorize/token'
                            for method, path in fake.calls))
        self.assertEqual(sum('/devices' in path for _, path in fake.calls), 2)
        self.client.force_login(self.owner_a)
        self.assertContains(self.client.get(reverse('networks:routers')), 'Connected')
        self.assertNotContains(self.client.get(reverse('networks:routers')), 'Beta EAP225')
        self.client.force_login(self.owner_b)
        self.assertContains(self.client.get(reverse('cloud:dashboard')), 'Offline')
        self.assertNotContains(self.client.get(reverse('cloud:dashboard')), 'Alpha EAP225')

    def test_stale_status_disappears_on_resubmission_or_failed_read_only_probe(self):
        profile = self.submit(self.owner_a, self.ap_a, 'AA:BB:CC:11:22:33')
        self.approve(profile, self.assignment('Alpha site', 'apiSiteA'))
        with patch('networks.omada_monitor.build_opener', return_value=ReadOnlyMultiSiteOmada()):
            poll_approved_managed()
        obs = OmadaDeviceObservation.objects.get(router=self.ap_a)
        obs.checked_at = timezone.now() - timedelta(minutes=3)
        obs.save(update_fields=['checked_at'])
        self.assertFalse(obs.is_fresh)
        with patch('networks.omada_monitor.build_opener', return_value=ReadOnlyMultiSiteOmada(sites=[])):
            statuses = poll_approved_managed()
        self.assertEqual(statuses[0].state, 'ERROR')
        self.client.force_login(self.owner_a)
        url = reverse('networks:omada_onboarding', args=[self.ap_a.pk])
        self.client.post(url, self.details('AA:BB:CC:11:22:33'))
        profile.refresh_from_db()
        self.assertIsNone(profile.managed_site_id)
        self.assertEqual(profile.status, 'SUBMITTED')
        self.assertFalse(OmadaDeviceObservation.objects.filter(router=self.ap_a).exists())

    def test_read_only_sites_list_command_uses_controller_not_customer_urls(self):
        fake = ReadOnlyMultiSiteOmada()
        with patch('networks.omada_monitor.build_opener', return_value=fake):
            out = io.StringIO()
            call_command('list_omada_sites', stdout=out)
        self.assertIn('Alpha site: apiSiteA', out.getvalue())
        self.assertNotIn('fake-read-only-secret', out.getvalue())

    def test_staff_https_csrf_still_requires_same_origin(self):
        profile = self.submit(self.owner_a, self.ap_a, 'AA:BB:CC:11:22:33')
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.staff)
        list_url = reverse('controlcenter:router_onboardings')
        page = browser.get(list_url, secure=True)
        self.assertEqual(page.headers['Referrer-Policy'], 'same-origin')
        review_url = reverse('controlcenter:review_router_onboarding', args=[profile.pk])
        data = self.assignment('Alpha site', 'apiSiteA') | {
            'csrfmiddlewaretoken': page.cookies['csrftoken'].value,
        }
        self.assertEqual(browser.post(review_url, data, secure=True).status_code, 403)
        self.assertEqual(browser.post(review_url, data, secure=True,
                                      HTTP_REFERER='https://testserver' + list_url).status_code, 302)
