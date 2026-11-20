"""Offline security and accounting tests. Never contact EvPay or the controller."""
import json
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from networks.models import WifiPlan
from portal.models import CaptivePortal
from tenants.models import Company, Membership
from wallets.models import BusinessWallet, SettledCollection
from .collections import start_collection, apply_collection_status
from .evpay import sign_payload
from .models import EvPayCollection, EvPayCollectionDelivery


PILOT = dict(
    EVPAY_ENABLED=True, EVPAY_ENVIRONMENT='sandbox',
    EVPAY_PRODUCTION_CHARGES_ENABLED=False,
    EVPAY_PUBLIC_CHECKOUT_ENABLED=True,
    EVPAY_COLLECTION_COMPANY_IDS={1},
    EVPAY_PUBLIC_MAX_AMOUNT_TZS=1000,
    EVPAY_BASE_URL='https://sandbox.evpay.co.tz',
    EVPAY_PUBLIC_BASE_URL='https://wifi.example.com',
    EVPAY_CLIENT_ID='test-client', EVPAY_CLIENT_SECRET='test-only',
    EVPAY_SIG_KEY='signing-key', EVPAY_WEBHOOK_SECRET='test-only-webhook',
    EVPAY_WEBHOOK_TOKEN='old-test-lab-token',
    EVPAY_COLLECTION_WEBHOOK_TOKEN='real-collections-test-token',
    OMADA_LIVE_ENABLED=True, OMADA_PILOT_COMPANY_ID=1,
    OMADA_CONTROLLER_URL='https://192.168.1.49:8043',
    OMADA_CONTROLLER_ID='a' * 32,
    OMADA_OPERATOR_NAME='operator', OMADA_OPERATOR_PASSWORD='test-only',
    OMADA_CA_FILE='', OMADA_AP_MAC='B8-FB-B3-79-B5-60', OMADA_SSID='WORLDLINK-TEST',
)


@override_settings(**PILOT)
class CollectionSafetyTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='WorldLink test operator')
        self.other = Company.objects.create(name='Different customer hotspot')
        self.assertEqual(self.company.pk, 1)
        self.plan = WifiPlan.objects.create(company=self.company, name='5-minute test',
                                            price=500, duration_minutes=5)
        CaptivePortal.objects.create(company=self.company, enabled=True)
        CaptivePortal.objects.create(company=self.other, enabled=True)
        user = get_user_model()
        self.owner = user.objects.create_user(username='worldlink-owner@example.com',
                                               password='StrongPassword123!')
        self.other_owner = user.objects.create_user(username='other-owner@example.com',
                                                     password='StrongPassword123!')
        self.staff = user.objects.create_superuser(username='worldlink-finance@example.com',
                                                   password='StrongPassword123!')
        Membership.objects.create(user=self.owner, company=self.company, role='OWNER')
        Membership.objects.create(user=self.other_owner, company=self.other, role='OWNER')
        self.context = {
            'clientMac': '12-34-56-78-90-AB', 'clientIp': '192.168.1.58',
            'apMac': 'B8-FB-B3-79-B5-60', 'ssidName': 'WORLDLINK-TEST', 'radioId': 0,
            'capturedAt': int(time.time()),
        }

    def _collection(self):
        obj, _ = start_collection(company=self.company, plan=self.plan, name='Customer One',
            phone='0712345678', operator='Mpesa', nonce=uuid.uuid4(), omada_context=self.context)
        return obj

    def _event(self, obj, *, amount=500, status='SUCCESS', event='payment.succeeded',
               delivery='first-delivery', valid=True):
        timestamp = int(time.time())
        body = json.dumps({'event': event, 'timestamp': timestamp, 'data': {
            'orderReference': obj.reference, 'status': status, 'amount': amount,
            'currency': 'TZS', 'id': 'gateway-ref-test'}}, separators=(',', ':')).encode()
        sig = sign_payload(PILOT['EVPAY_WEBHOOK_SECRET'], timestamp, body)
        return self.client.post(reverse('payments:collection_webhook',
            kwargs={'token': 'real-collections-test-token'}), data=body,
            content_type='application/json', HTTP_X_EVPAY_DELIVERY=delivery,
            HTTP_X_EVPAY_EVENT=event,
            HTTP_X_EVPAY_SIGNATURE=f't={timestamp},v1={sig if valid else "0" * 64}')

    def test_payment_never_activates_router_before_signed_success(self):
        obj = self._collection()
        with patch('payments.management.commands.activate_evpay_omada.authorize_paid_collection') as authorize:
            call_command('activate_evpay_omada')
        authorize.assert_not_called()
        self.assertIsNone(obj.omada_activated_at)
        self.assertEqual(BusinessWallet.objects.count(), 0)

    def test_signed_callback_deduplicates_and_worker_activates_once(self):
        obj = self._collection()
        self.assertEqual(self._event(obj).status_code, 200)
        self.assertEqual(self._event(obj).status_code, 200)
        self.assertEqual(EvPayCollectionDelivery.objects.count(), 1)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'SUCCESS')
        with patch('payments.management.commands.activate_evpay_omada.authorize_paid_collection',
                   return_value=True) as authorize:
            call_command('activate_evpay_omada')
            call_command('activate_evpay_omada')
        authorize.assert_called_once()
        obj.refresh_from_db()
        self.assertIsNotNone(obj.omada_activated_at)
        self.assertEqual(BusinessWallet.objects.count(), 0)

    def test_invalid_signature_and_amount_cannot_create_earnings(self):
        obj = self._collection()
        self.assertEqual(self._event(obj, valid=False).status_code, 401)
        self.assertEqual(self._event(obj, amount=999).status_code, 400)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'CREATED')
        self.assertIsNone(obj.confirmed_at)

    def test_webhook_diagnostics_distinguish_wrong_key_without_accepting_it(self):
        obj = self._collection()
        timestamp = int(time.time())
        body = json.dumps({'event': 'payment.succeeded', 'timestamp': timestamp, 'data': {
            'orderReference': obj.reference, 'status': 'SUCCESS', 'amount': 500,
            'currency': 'TZS'}}, separators=(',', ':')).encode()
        # The API request signing key is NOT automatically trusted for callbacks.
        signature = sign_payload(PILOT['EVPAY_SIG_KEY'], timestamp, body)
        url = reverse('payments:collection_webhook',
                      kwargs={'token': PILOT['EVPAY_COLLECTION_WEBHOOK_TOKEN']})
        with self.assertLogs('payments.collection_views', level='WARNING') as caught:
            res = self.client.post(url, data=body, content_type='application/json',
                HTTP_X_EVPAY_SIGNATURE=f't={timestamp},v1={signature}')
        self.assertEqual(res.status_code, 401)
        self.assertIn('matches API request-signing key', caught.output[0])
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'CREATED')

    def test_webhook_diagnostics_identify_expired_signature_without_accepting_it(self):
        obj = self._collection()
        timestamp = int(time.time()) - 600
        body = b'{}'
        signature = sign_payload(PILOT['EVPAY_WEBHOOK_SECRET'], timestamp, body)
        url = reverse('payments:collection_webhook',
                      kwargs={'token': PILOT['EVPAY_COLLECTION_WEBHOOK_TOKEN']})
        with self.assertLogs('payments.collection_views', level='WARNING') as caught:
            res = self.client.post(url, data=body, content_type='application/json',
                HTTP_X_EVPAY_SIGNATURE=f't={timestamp},v1={signature}')
        self.assertEqual(res.status_code, 401)
        self.assertIn('outside five-minute window', caught.output[0])
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'CREATED')

    def test_failed_reversed_payments_cannot_authorize(self):
        obj = self._collection()
        apply_collection_status(reference=obj.reference, status='FAILED', amount=500, currency='TZS')
        with patch('payments.management.commands.activate_evpay_omada.authorize_paid_collection') as auth:
            call_command('activate_evpay_omada')
        auth.assert_not_called()

    def test_other_business_cannot_see_payment_records(self):
        obj = self._collection()
        self._event(obj)
        self.client.force_login(self.other_owner)
        res = self.client.get(reverse('payments:business_collections'))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, obj.reference)
        res = self.client.get(reverse('wallets:dashboard'))
        self.assertNotContains(res, obj.reference)
        self.assertNotContains(res, 'TZS 500')
        self.assertEqual(self.client.post(reverse('payments:collection_reconcile', args=[obj.pk])).status_code, 404)

    def test_public_checkout_requires_captive_context_and_no_duplicate_push(self):
        checkout = reverse('portal:evpay_checkout', args=[self.company.slug, self.plan.pk])
        res = self.client.get(checkout)
        self.assertEqual(res.status_code, 200)
        nonce = self.client.session['whc_evpay_checkout_nonce']
        body = {'nonce': nonce, 'customer_name': 'Customer One', 'phone': '0712345678',
                'operator': 'Mpesa', 'authorized': 'on'}
        with patch('portal.views.initiate_collection') as push:
            result = self.client.post(checkout, body)
        self.assertEqual(result.status_code, 200)
        push.assert_not_called()
        self.assertEqual(EvPayCollection.objects.count(), 0)
        self.client.get(reverse('portal:public', args=[self.company.slug]), {
            **self.context, 't': int(time.time() * 1000)})
        with patch('portal.views.initiate_collection', return_value={'transactionId': 'tx-test'}) as push:
            result = self.client.post(checkout, body)
            self.assertEqual(result.status_code, 302)
            push.assert_called_once()
        obj = EvPayCollection.objects.get()
        self.assertEqual(obj.client_mac, self.context['clientMac'])
        self.assertEqual(obj.status, 'PENDING')

    def test_omada_redirect_supports_seconds_and_milliseconds_but_not_stale_time(self):
        url = reverse('portal:public', args=[self.company.slug])
        now = int(time.time())
        for timestamp in (now, now * 1000):
            response = self.client.get(url, {**self.context, 't': timestamp})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Pay with mobile money')

        for timestamp in (now - 600, (now + 600) * 1000, now * 100):
            session = self.client.session
            session.pop(f'whc_omada_client_{self.company.pk}', None)
            session.save()
            response = self.client.get(url, {**self.context, 't': timestamp})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'Pay with mobile money')

    def test_checkout_requires_csrf_and_allows_same_origin_https_referer(self):
        checkout = reverse('portal:evpay_checkout', args=[self.company.slug, self.plan.pk])
        browser = Client(enforce_csrf_checks=True)
        response = browser.get(checkout, secure=True)
        self.assertContains(response, '<meta name="referrer" content="same-origin">')
        self.assertEqual(browser.post(checkout, {}, secure=True).status_code, 403)
        token = browser.cookies['csrftoken'].value
        response = browser.post(checkout, {'csrfmiddlewaretoken': token}, secure=True,
                                HTTP_REFERER='https://testserver' + checkout)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EvPayCollection.objects.count(), 0)

    def test_finance_clearance_requires_real_evidence_and_never_credits_twice(self):
        obj = self._collection()
        self._event(obj)
        url = reverse('wallets:evpay_clearance', args=[obj.pk])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url, {'settlement_reference': 'bank-statement-007'}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(url, {'settlement_reference': 'x'}).status_code, 302)
        self.assertEqual(BusinessWallet.objects.count(), 0)
        self.assertEqual(self.client.post(url, {'settlement_reference': 'BANK-STATEMENT-007'}).status_code, 302)
        self.assertEqual(self.client.post(url, {'settlement_reference': 'BANK-STATEMENT-007'}).status_code, 302)
        wallet = BusinessWallet.objects.get(company=self.company)
        self.assertEqual(wallet.available, Decimal(500))
        self.assertEqual(SettledCollection.objects.count(), 1)
        self.assertFalse(BusinessWallet.objects.filter(company=self.other).exists())

    def test_read_only_reconcile_never_issues_second_payment(self):
        obj = self._collection()
        EvPayCollection.objects.filter(pk=obj.pk).update(
            status='PENDING', created_at=timezone.now() - timedelta(minutes=8))
        result = {'customReference': obj.reference, 'status': 'SUCCESS',
                  'amount': 500, 'currency': 'TZS', 'transRef': 'test-provider-ref'}
        with patch('payments.management.commands.reconcile_evpay_collections.retrieve_ussd',
                   return_value=result) as check, patch('payments.evpay.initiate_collection') as push:
            call_command('reconcile_evpay_collections')
            check.assert_called_once_with(obj.reference)
            push.assert_not_called()
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'SUCCESS')
        self.assertIsNone(obj.omada_activated_at)

    def test_fast_reconcile_checks_recent_payment_and_never_recharges(self):
        obj = self._collection()
        EvPayCollection.objects.filter(pk=obj.pk).update(
            status='PENDING', created_at=timezone.now() - timedelta(seconds=8))
        result = {'customReference': obj.reference, 'status': 'SUCCESS',
                  'amount': 500, 'currency': 'TZS'}
        with patch('payments.management.commands.reconcile_evpay_collections.retrieve_ussd',
                   return_value=result) as check, patch('payments.evpay.initiate_collection') as push:
            call_command('reconcile_evpay_collections', '--fast')
            check.assert_called_once_with(obj.reference)
            push.assert_not_called()
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'SUCCESS')
        self.assertIsNone(obj.omada_activated_at)

    def test_fast_reconcile_respects_per_payment_backoff(self):
        obj = self._collection()
        EvPayCollection.objects.filter(pk=obj.pk).update(
            status='PENDING', created_at=timezone.now() - timedelta(seconds=8),
            last_checked_at=timezone.now())
        with patch('payments.management.commands.reconcile_evpay_collections.retrieve_ussd') as check:
            call_command('reconcile_evpay_collections', '--fast')
            check.assert_not_called()
