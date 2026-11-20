"""No live payment or Omada calls: tenant and replay tests for printed vouchers."""

import time
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from networks.models import (Location, OmadaDeviceObservation, OmadaManagedSite,
                             OmadaOnboarding, Router, WifiPlan)
from payments.models import EvPayCollection
from portal.models import CaptivePortal
from tenants.models import Company, Membership
from vouchers.models import ManualSale, Voucher, VoucherBatch, VoucherRedemption
from vouchers.services import VoucherError, approved_voucher_route, redeem_voucher


VOUCHER_SETTINGS = dict(
    OMADA_LIVE_ENABLED=True, OMADA_PILOT_COMPANY_ID=1,
    OMADA_CONTROLLER_URL='https://omada.example.com', OMADA_CONTROLLER_ID='a' * 32,
    OMADA_OPERATOR_NAME='voucher-operator', OMADA_OPERATOR_PASSWORD='test-only',
    OMADA_CA_FILE='', OMADA_AP_MAC='B8-FB-B3-79-B5-60', OMADA_SSID='LEGACY-PILOT',
    EVPAY_MULTITENANT_ENABLED=False, EVPAY_COLLECTION_COMPANY_IDS={1},
    EVPAY_ENABLED=False, EVPAY_PUBLIC_CHECKOUT_ENABLED=False,
    WHC_REDIS_URL='redis://127.0.0.1:6379/1',
)


@override_settings(**VOUCHER_SETTINGS)
class VoucherOmadaTests(TestCase):
    def setUp(self):
        self.old = Company.objects.create(name='Old pilot', status='ACTIVE')
        self.company = Company.objects.create(name='New business', status='ACTIVE')
        self.other = Company.objects.create(name='Other business', status='ACTIVE')
        CaptivePortal.objects.create(company=self.company, enabled=True)
        CaptivePortal.objects.create(company=self.other, enabled=True)
        self.staff = get_user_model().objects.create_superuser(username='voucher-staff', password='pw')
        self.owner = get_user_model().objects.create_user(username='voucher-owner', password='pw')
        Membership.objects.create(company=self.company, user=self.owner, role='OWNER')
        self.plan = WifiPlan.objects.create(company=self.company, name='5 minute voucher',
                                             duration_minutes=5, price=100)
        self.batch = VoucherBatch.objects.create(company=self.company, plan=self.plan,
                                                  quantity=3, created_by=self.owner)
        self.voucher = Voucher.objects.create(company=self.company, batch=self.batch, code='WHC-ABCDEF2345')
        self.router = Router.objects.create(company=self.company, name='Real EAP',
            family='OMADA', location=Location.objects.create(company=self.company, name='Main'))
        self.site = OmadaManagedSite.objects.create(company=self.company, name='Real site',
            inform_site_id='c' * 32, openapi_site_id='realSite')
        self.profile = OmadaOnboarding.objects.create(router=self.router, status='REVIEWED',
            reviewed_by=self.staff, connection_mode='CENTRAL', managed_site=self.site,
            ap_mac='AA-BB-CC-11-22-33', ssid_name='NEW-WIFI')
        self.observation = OmadaDeviceObservation.objects.create(
            router=self.router, state='CONNECTED', checked_at=timezone.now())
        self.context = dict(clientMac='12-34-56-78-90-AB', clientIp='192.168.10.4',
                            apMac=self.profile.ap_mac, ssidName='NEW-WIFI', radioId=0,
                            capturedAt=int(time.time()))

    def approve(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('controlcenter:router_voucher_access', args=[self.profile.pk]),
                         {'decision': 'enable', 'hotspot_verified': 'yes'})
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.voucher_access_approved_at)
        self.client.logout()

    def sell(self):
        self.voucher.status = Voucher.Status.SOLD
        self.voucher.save(update_fields=['status'])
        ManualSale.objects.create(company=self.company, voucher=self.voucher,
                                  amount=self.plan.price, method='CASH', recorded_by=self.owner)

    def portal_context(self):
        result = self.client.get(reverse('portal:public', args=[self.company.slug]), {
            'clientMac': self.context['clientMac'].replace('-', ':'),
            'clientIp': self.context['clientIp'], 'apMac': self.context['apMac'],
            'ssidName': self.context['ssidName'], 'radioId': '0', 't': str(int(time.time())),
        })
        return result

    def test_manual_sale_uses_own_page_and_preserves_sale_rules(self):
        self.client.force_login(self.owner)
        url = reverse('vouchers:sell', args=[self.voucher.pk])
        batch_url = reverse('vouchers:batch_detail', args=[self.batch.pk])
        batch = self.client.get(batch_url)
        self.assertContains(batch, url)
        self.assertNotContains(batch, '<select name="method"')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.voucher.code)
        self.assertContains(response, 'Confirm sale')
        self.assertEqual(self.client.post(url, {'method': 'INVALID'}).status_code, 400)
        self.assertFalse(ManualSale.objects.filter(voucher=self.voucher).exists())
        self.assertEqual(self.client.post(url, {'method': 'CASH'}).status_code, 302)
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.status, Voucher.Status.SOLD)
        self.assertEqual(ManualSale.objects.get(voucher=self.voucher).amount, self.plan.price)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.post(url, {'method': 'BANK'}).status_code, 302)
        self.assertEqual(ManualSale.objects.filter(voucher=self.voucher).count(), 1)
        self.assertEqual(EvPayCollection.objects.count(), 0)

    def test_manual_sale_page_respects_tenant_and_csrf(self):
        self.client.force_login(self.owner)
        foreign_voucher = Voucher.objects.create(company=self.other,
            batch=VoucherBatch.objects.create(company=self.other,
                plan=WifiPlan.objects.create(company=self.other, name='Other plan',
                    duration_minutes=5, price=100), quantity=1, created_by=self.owner),
            code='WHC-OTHERABC23')
        self.assertEqual(self.client.get(reverse('vouchers:sell', args=[foreign_voucher.pk])).status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        url = reverse('vouchers:sell', args=[self.voucher.pk])
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url, {'method': 'CASH'}).status_code, 403)
        self.assertFalse(ManualSale.objects.filter(voucher=self.voucher).exists())

    def test_new_business_needs_independent_staff_approval_and_online_router(self):
        self.assertFalse(approved_voucher_route(self.company, self.context['apMac'], 'NEW-WIFI'))
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('controlcenter:router_voucher_access',
                         args=[self.profile.pk]), {'decision': 'enable'}).status_code, 403)
        self.client.logout()
        self.client.force_login(self.staff)
        self.client.post(reverse('controlcenter:router_voucher_access', args=[self.profile.pk]),
                         {'decision': 'enable'})
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.voucher_access_approved_at)
        self.client.logout()
        self.approve()
        self.assertTrue(approved_voucher_route(self.company, self.context['apMac'], 'NEW-WIFI'))
        self.assertFalse(approved_voucher_route(self.other, self.context['apMac'], 'NEW-WIFI'))
        self.assertFalse(approved_voucher_route(self.company, self.context['apMac'], 'FORGED'))
        self.observation.checked_at = timezone.now() - timedelta(minutes=4)
        self.observation.save()
        self.assertFalse(approved_voucher_route(self.company, self.context['apMac'], 'NEW-WIFI'))

    def test_no_sale_no_access_and_one_mac_only(self):
        self.approve()
        with self.assertRaises(VoucherError):
            redeem_voucher(company=self.company, raw_code=self.voucher.code, context=self.context)
        self.sell()
        with patch('vouchers.services._authorize_external_guest', return_value=True) as api:
            first = redeem_voucher(company=self.company, raw_code=self.voucher.code, context=self.context)
            self.assertEqual(first.client_mac, self.context['clientMac'])
            self.assertEqual(api.call_count, 1)
            self.assertLessEqual(api.call_args.kwargs['remaining_ms'], 300000)
            again = redeem_voucher(company=self.company, raw_code=self.voucher.code, context=self.context)
            self.assertEqual(first.pk, again.pk)
        self.assertEqual(VoucherRedemption.objects.count(), 1)
        altered = self.context | {'clientMac': '56-34-56-78-90-AB'}
        with self.assertRaisesMessage(VoucherError, 'different device'):
            redeem_voucher(company=self.company, raw_code=self.voucher.code, context=altered)
        self.assertEqual(EvPayCollection.objects.count(), 0)

    def test_controller_error_can_retry_without_extending_expiry(self):
        self.approve()
        self.sell()
        from payments.omada import OmadaError
        with patch('vouchers.services._authorize_external_guest', side_effect=OmadaError('down')):
            with self.assertRaisesMessage(VoucherError, 'Could not confirm'):
                redeem_voucher(company=self.company, raw_code=self.voucher.code, context=self.context)
        first = VoucherRedemption.objects.get()
        with patch('vouchers.services._authorize_external_guest', return_value=True):
            redeem_voucher(company=self.company, raw_code=self.voucher.code, context=self.context)
        first.refresh_from_db()
        self.assertEqual(first.expires_at, first.claimed_at + timedelta(minutes=5))
        self.assertIsNotNone(first.activated_at)
        first.expires_at = timezone.now() - timedelta(seconds=1)
        first.save()
        with patch('vouchers.services._authorize_external_guest') as api:
            with self.assertRaisesMessage(VoucherError, 'expired'):
                redeem_voucher(company=self.company, raw_code=self.voucher.code, context=self.context)
        api.assert_not_called()

    def test_captive_ui_real_redirect_not_manually_opened_page(self):
        self.approve()
        direct = self.client.get(reverse('portal:public', args=[self.company.slug]))
        self.assertNotContains(direct, 'Activate my internet')
        captured = self.portal_context()
        self.assertContains(captured, 'Activate my internet')
        self.assertEqual(captured['Referrer-Policy'], 'same-origin')
        self.assertFalse(captured.context['evpay_available'])
        self.sell()
        with patch('vouchers.services._authorize_external_guest', return_value=True):
            response = self.client.post(reverse('portal:voucher_redeem', args=[self.company.slug]),
                                        {'code': self.voucher.code.lower()})
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.url)
        self.assertContains(page, 'Wi-Fi activated')
        self.assertNotContains(page, self.voucher.code)
        self.assertEqual(self.client.get(reverse('portal:voucher_status',
            args=[self.other.slug, VoucherRedemption.objects.get().public_id])).status_code, 404)

    def test_public_redeem_protected_by_csrf_and_tenant_isolation(self):
        self.approve()
        self.sell()
        client = Client(enforce_csrf_checks=True)
        url = reverse('portal:voucher_redeem', args=[self.company.slug])
        self.assertEqual(client.post(url, {'code': self.voucher.code}).status_code, 403)
        with self.assertRaises(VoucherError):
            redeem_voucher(company=self.other, raw_code=self.voucher.code, context=self.context)
        self.portal_context()
        response = self.client.post(reverse('portal:voucher_redeem', args=[self.other.slug]),
                                    {'code': self.voucher.code})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VoucherRedemption.objects.exists())

    def test_staff_revoke_blocks_new_redemptions_without_touching_evpay(self):
        self.approve()
        self.sell()
        self.client.force_login(self.staff)
        self.client.post(reverse('controlcenter:router_voucher_access', args=[self.profile.pk]),
                         {'decision': 'disable'})
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.voucher_access_approved_at)
        with self.assertRaises(VoucherError):
            redeem_voucher(company=self.company, raw_code=self.voucher.code, context=self.context)
