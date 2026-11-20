"""Fail-closed multi-business payment authorization; completely offline tests."""
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from payments.collections import approved_payment_route, collection_enabled_for, start_collection
from payments.models import EvPayCollection
from payments.omada import OmadaError, authorize_paid_collection, controller_context
from tenants.models import Company, Membership
from .models import (Location, OmadaDeviceObservation, OmadaManagedSite,
                     OmadaOnboarding, Router, WifiPlan)


SETTINGS = dict(
    EVPAY_ENABLED=True, EVPAY_ENVIRONMENT='sandbox',
    EVPAY_PRODUCTION_CHARGES_ENABLED=False, EVPAY_PUBLIC_CHECKOUT_ENABLED=True,
    EVPAY_MULTITENANT_ENABLED=True, EVPAY_COLLECTION_COMPANY_IDS={2},
    EVPAY_PUBLIC_MAX_AMOUNT_TZS=1000, EVPAY_BASE_URL='https://sandbox.evpay.co.tz',
    EVPAY_PUBLIC_BASE_URL='https://wifi.example.com',
    EVPAY_CLIENT_ID='client', EVPAY_CLIENT_SECRET='test-only', EVPAY_SIG_KEY='signing-key',
    EVPAY_WEBHOOK_SECRET='webhook-secret', EVPAY_WEBHOOK_TOKEN='legacy-webhook',
    EVPAY_COLLECTION_WEBHOOK_TOKEN='webhook-token',
    OMADA_LIVE_ENABLED=True, OMADA_PILOT_COMPANY_ID=1,
    OMADA_CONTROLLER_URL='https://omada.example.com', OMADA_CONTROLLER_ID='a' * 32,
    OMADA_OPERATOR_NAME='operator', OMADA_OPERATOR_PASSWORD='test', OMADA_CA_FILE='',
    OMADA_AP_MAC='B8-FB-B3-79-B5-60', OMADA_SSID='PILOT-SSID',
)


@override_settings(**SETTINGS)
class MultiBusinessPaymentGateTests(TestCase):
    def setUp(self):
        self.pilot = Company.objects.create(name='Legacy pilot')
        self.company = Company.objects.create(name='Second operator', status='ACTIVE')
        self.outsider = Company.objects.create(name='Third operator', status='ACTIVE')
        self.staff = get_user_model().objects.create_superuser(username='staff-live', password='pass')
        self.owner = get_user_model().objects.create_user(username='new-shop-owner', password='pass')
        Membership.objects.create(company=self.company, user=self.owner, role='OWNER')
        self.plan = WifiPlan.objects.create(company=self.company, name='5 minutes', price=100,
                                            duration_minutes=5)
        self.router = Router.objects.create(company=self.company,
            location=Location.objects.create(company=self.company, name='Shop'),
            name='Second router', family='OMADA', model_name='EAP225', serial='EAP-SECOND')
        self.site = OmadaManagedSite.objects.create(company=self.company, name='Second site',
            inform_site_id='b' * 32, openapi_site_id='siteSecond')
        self.profile = OmadaOnboarding.objects.create(router=self.router,
            status='REVIEWED', connection_mode='CENTRAL', managed_site=self.site,
            reviewed_by=self.staff, reviewed_at=timezone.now(),
            ap_mac='AA-BB-CC-11-22-33', ssid_name='SECOND-WIFI')
        self.context = dict(clientMac='12-34-56-78-90-AB', clientIp='192.168.1.40',
            apMac='AA-BB-CC-11-22-33', ssidName='SECOND-WIFI', radioId=0,
            capturedAt=int(time.time()))

    def enable(self):
        self.client.force_login(self.staff)
        return self.client.post(reverse('controlcenter:router_live_payments', args=[self.profile.pk]),
            {'decision': 'enable', 'provider_authorized': 'yes', 'test_verified': 'yes'})

    def test_review_is_not_financial_approval_and_staff_page_is_protected(self):
        self.assertFalse(collection_enabled_for(self.company))
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('controlcenter:router_onboarding_detail', args=[self.profile.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('controlcenter:router_live_payments', args=[self.profile.pk]),
                                     {'decision': 'enable'}).status_code, 403)
        self.assertFalse(self.profile.live_payments_approved_at)
        self.client.force_login(self.staff)
        page = self.client.get(reverse('controlcenter:router_onboarding_detail', args=[self.profile.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers['Referrer-Policy'], 'same-origin')
        self.assertContains(page, 'WorldLink')
        self.assertContains(page, 'Live Wi-Fi payment authorization')

    def test_online_check_and_explicit_attestation_required(self):
        self.enable()
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.live_payments_approved_at)
        observation = OmadaDeviceObservation.objects.create(router=self.router,
            state='CONNECTED', checked_at=timezone.now())
        self.client.force_login(self.staff)
        self.client.post(reverse('controlcenter:router_live_payments', args=[self.profile.pk]),
                         {'decision': 'enable'})
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.live_payments_approved_at)
        self.enable()
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.live_payments_approved_at)
        self.assertTrue(collection_enabled_for(self.company))
        observation.checked_at = timezone.now() - timedelta(minutes=5)
        observation.save()
        self.client.post(reverse('controlcenter:router_live_payments', args=[self.profile.pk]),
                         {'decision': 'disable'})
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.live_payments_approved_at)
        self.assertFalse(collection_enabled_for(self.company))

    def test_tenant_route_isolated_and_payment_status_never_directly_creates_wallet(self):
        OmadaDeviceObservation.objects.create(router=self.router, state='CONNECTED',
                                               checked_at=timezone.now())
        self.enable()
        self.assertTrue(approved_payment_route(self.company.pk, self.context['apMac'], 'SECOND-WIFI'))
        self.assertFalse(approved_payment_route(self.outsider.pk, self.context['apMac'], 'SECOND-WIFI'))
        self.assertFalse(approved_payment_route(self.company.pk, self.context['apMac'], 'OTHER-WIFI'))
        self.assertFalse(approved_payment_route(self.company.pk, SETTINGS['OMADA_AP_MAC'], 'PILOT-SSID'))
        self.assertFalse(collection_enabled_for(self.outsider))
        with self.assertRaises(ValueError):
            start_collection(company=self.company, plan=self.plan, name='Customer',
                phone='0712345678', operator='Mpesa', nonce=uuid.uuid4(),
                omada_context=self.context | {'ssidName': 'FORGED'})
        payment, created = start_collection(company=self.company, plan=self.plan,
            name='Customer', phone='0712345678', operator='Mpesa', nonce=uuid.uuid4(),
            omada_context=self.context)
        self.assertTrue(created)
        self.assertEqual(payment.status, 'CREATED')
        with patch('payments.management.commands.activate_evpay_omada.authorize_paid_collection') as auth:
            call_command('activate_evpay_omada')
        auth.assert_not_called()
        payment.status = 'SUCCESS'
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=['status', 'confirmed_at'])
        with patch('payments.management.commands.activate_evpay_omada.authorize_paid_collection') as auth:
            call_command('activate_evpay_omada')
        auth.assert_called_once()
        self.assertTrue(EvPayCollection.objects.get(pk=payment.pk).omada_activated_at)
        self.assertFalse(hasattr(self.company, 'worldlink_wallet'))

    def test_live_collection_is_blocked_after_revocation_and_global_gate_off(self):
        OmadaDeviceObservation.objects.create(router=self.router, state='CONNECTED',
                                               checked_at=timezone.now())
        self.enable()
        with override_settings(EVPAY_MULTITENANT_ENABLED=False):
            self.assertFalse(collection_enabled_for(self.company))
        with override_settings(EVPAY_COLLECTION_COMPANY_IDS={1}):
            self.assertFalse(collection_enabled_for(self.company))
        payment, _ = start_collection(company=self.company, plan=self.plan,
            name='Customer', phone='0712345678', operator='Mpesa', nonce=uuid.uuid4(),
            omada_context=self.context)
        payment.status = 'SUCCESS'
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=['status', 'confirmed_at'])
        self.client.force_login(self.staff)
        self.client.post(reverse('controlcenter:router_live_payments', args=[self.profile.pk]),
                         {'decision': 'disable'})
        with self.assertRaises(OmadaError):
            authorize_paid_collection(payment)
        self.assertFalse(EvPayCollection.objects.get(pk=payment.pk).omada_activated_at)

    def test_expired_payment_cannot_starve_a_new_authorization(self):
        OmadaDeviceObservation.objects.create(router=self.router, state='CONNECTED',
                                               checked_at=timezone.now())
        self.enable()
        old_payment, _ = start_collection(company=self.company, plan=self.plan,
            name='Expired buyer', phone='0712345678', operator='Mpesa', nonce=uuid.uuid4(),
            omada_context=self.context)
        new_payment, _ = start_collection(company=self.company, plan=self.plan,
            name='Fresh buyer', phone='0712345678', operator='Mpesa', nonce=uuid.uuid4(),
            omada_context=self.context)
        old_payment.status = 'SETTLED'
        old_payment.confirmed_at = timezone.now() - timedelta(minutes=9)
        old_payment.omada_last_error = 'Paid package expired before the controller was reachable; contact support.'
        old_payment.save(update_fields=['status', 'confirmed_at', 'omada_last_error'])
        new_payment.status = 'SUCCESS'
        new_payment.confirmed_at = timezone.now()
        new_payment.save(update_fields=['status', 'confirmed_at'])
        with patch('payments.management.commands.activate_evpay_omada.authorize_paid_collection') as auth:
            call_command('activate_evpay_omada', limit=1)
        auth.assert_called_once()
        self.assertEqual(auth.call_args.args[0].pk, new_payment.pk)

    def test_verified_revenue_is_tenant_only_and_not_withdrawable(self):
        OmadaDeviceObservation.objects.create(router=self.router, state='CONNECTED',
                                               checked_at=timezone.now())
        self.enable()
        payment, _ = start_collection(company=self.company, plan=self.plan,
            name='Portal buyer', phone='0712345678', operator='Mpesa', nonce=uuid.uuid4(),
            omada_context=self.context)
        payment.status = 'SUCCESS'
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=['status', 'confirmed_at'])
        self.client.force_login(self.owner)
        page = self.client.get(reverse('cloud:dashboard'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'TZS 100')
        self.assertContains(page, 'Awaiting cleared settlement')
        self.assertContains(page, 'Available to withdraw')
        self.assertEqual(page.context['wallet_available'], 0)
        outsider_owner = get_user_model().objects.create_user(username='third-shop-owner', password='pass')
        Membership.objects.create(company=self.outsider, user=outsider_owner, role='OWNER')
        self.client.force_login(outsider_owner)
        other_page = self.client.get(reverse('cloud:dashboard'))
        self.assertEqual(other_page.status_code, 200)
        self.assertEqual(other_page.context['evpay_confirmed_total'], 0)
        self.assertEqual(other_page.context['evpay_awaiting_clearance'], 0)
        self.assertNotContains(other_page, payment.reference)
