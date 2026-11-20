from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from networks.models import (Location, OmadaDeviceObservation, OmadaManagedSite,
                             OmadaOnboarding, Router, WifiPlan)
from networks.omada_monitor import _sync_managed_clients
from payments.models import EvPayCollection
from tenants.models import Company, Membership
from .models import OmadaClientObservation
from .omada_clients import live_omada_clients


class ClientInventoryTests(TestCase):
    def setUp(self):
        user = get_user_model()
        self.owner = user.objects.create_user(username='omada-owner', password='password333!')
        self.company = Company.objects.create(name='Our shop')
        self.other = Company.objects.create(name='Other business')
        Membership.objects.create(company=self.company, user=self.owner, role='OWNER')
        location = Location.objects.create(company=self.company, name='Main')
        self.router = Router.objects.create(company=self.company, location=location,
                                            family=Router.Family.OMADA, name='Shop AP')
        site = OmadaManagedSite.objects.create(company=self.company, name='Site A',
                                               inform_site_id='abcdef0123456789', openapi_site_id='abcdef0123456789')
        OmadaOnboarding.objects.create(router=self.router, managed_site=site,
                                      status=OmadaOnboarding.Status.REVIEWED, reviewed_by=self.owner,
                                      connection_mode=OmadaOnboarding.ConnectionMode.CENTRAL,
                                      ap_mac='B8-FB-B3-79-B5-60', ssid_name='OUR-WIFI')
        self.observation = OmadaDeviceObservation.objects.create(
            router=self.router, state=OmadaDeviceObservation.State.CONNECTED,
            checked_at=timezone.now())

    def test_only_matching_ap_and_ssid_clients_are_recorded(self):
        class FakeReadOnly:
            def get_connected_clients(self, **kwargs):
                return [
                    {'mac':'AA-BB-CC-DD-EE-01','apMac':'B8-FB-B3-79-B5-60','ssid':'OUR-WIFI','ip':'10.1.1.10','deviceType':'Phone'},
                    {'mac':'AA-BB-CC-DD-EE-02','apMac':'B8-FB-B3-79-B5-60','ssid':'WRONG-WIFI','ip':'10.1.1.11'},
                    {'mac':'AA-BB-CC-DD-EE-03','apMac':'11-22-33-44-55-66','ssid':'OUR-WIFI','ip':'10.1.1.12'},
                ]
        _sync_managed_clients(FakeReadOnly(), [self.router], [self.observation])
        self.assertEqual(OmadaClientObservation.objects.filter(company=self.company).count(), 1)
        entry = OmadaClientObservation.objects.get(company=self.company)
        self.assertTrue(entry.online)
        self.assertEqual(entry.ip_address, '10.1.1.10')
        self.assertEqual(entry.device_type, 'Phone')
        entry.observed_at = timezone.now() - timedelta(minutes=4)
        entry.save(update_fields=['observed_at'])
        self.assertFalse(entry.online)

    def test_complete_next_read_marks_missing_client_offline(self):
        item = OmadaClientObservation.objects.create(company=self.company, router=self.router,
                                                     mac_address='AA-BB-CC-DD-EE-01',
                                                     ssid_name='OUR-WIFI', observed_at=timezone.now())
        class EmptyClientList:
            def get_connected_clients(self, **kwargs):
                return []
        _sync_managed_clients(EmptyClientList(), [self.router], [self.observation])
        item.refresh_from_db()
        self.assertFalse(item.online)

    def test_paid_customer_identity_requires_matching_activated_entitlement(self):
        OmadaClientObservation.objects.create(company=self.company,router=self.router,
                                             mac_address='AA-BB-CC-DD-EE-01',ssid_name='OUR-WIFI',
                                             observed_at=timezone.now(), ip_address='10.1.1.10')
        plan = WifiPlan.objects.create(company=self.company, name='FIVE MINS', duration_minutes=5, price=100)
        EvPayCollection.objects.create(company=self.company, plan=plan, checkout_nonce=uuid4(),
                                       reference='WHC-CLIENT-TEST', customer_name='Real Payee',
                                       phone='255710123456', operator='Mpesa', amount=100,
                                       environment='live', status='SUCCESS', confirmed_at=timezone.now(),
                                       omada_activated_at=timezone.now(), client_mac='AA-BB-CC-DD-EE-01',
                                       ap_mac='B8-FB-B3-79-B5-60',ssid_name='OUR-WIFI')
        entries = live_omada_clients(self.company)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['name'], 'Real Payee')
        self.assertEqual(entries[0]['package'], 'FIVE MINS')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('hotspots:sessions')), 'Real Payee')
        self.assertContains(self.client.get(reverse('hotspots:customers')), 'Real Payee')
        self.assertEqual(len(live_omada_clients(self.other)), 0)

    def test_stale_or_unapproved_ap_is_not_shown_online(self):
        entry = OmadaClientObservation.objects.create(company=self.company,router=self.router,
                                                       mac_address='AA-BB-CC-DD-EE-01',ssid_name='OUR-WIFI',
                                                       observed_at=timezone.now())
        self.assertTrue(entry.online)
        self.observation.checked_at = timezone.now() - timedelta(minutes=5)
        self.observation.save(update_fields=['checked_at'])
        self.assertFalse(entry.online)
        self.assertEqual(live_omada_clients(self.company), [])
