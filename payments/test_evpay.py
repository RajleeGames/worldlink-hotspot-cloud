"""Security-focused tests for isolated EvPay pilot. No real network calls."""
import json
import time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from tenants.models import Company, Membership
from .evpay import normalize_msisdn, sign_payload, verify_webhook, EvPayError, ensure_settings_ready
from .models import EvPayTestPayment, EvPayDelivery, PaymentOrder
from .evpay_lab import apply_status


class SigningTests(SimpleTestCase):
    def test_signature_and_replay_protection(self):
        raw = b'{"event":"payment.succeeded"}'
        t = int(time.time())
        signature = sign_payload('testing-secret', t, raw)
        self.assertTrue(verify_webhook(raw, f't={t},v1={signature}', 'testing-secret', now=t))
        self.assertFalse(verify_webhook(raw + b' ', f't={t},v1={signature}', 'testing-secret', now=t))
        self.assertFalse(verify_webhook(raw, f't={t},v1={signature}', 'other-secret', now=t))
        self.assertFalse(verify_webhook(raw, f't={t},v1={signature}', 'testing-secret', now=t + 301))
        self.assertFalse(verify_webhook(raw, '', 'testing-secret', now=t))

    def test_tanzanian_phone_normalization(self):
        self.assertEqual(normalize_msisdn('0712 345 678'), '255712345678')
        self.assertEqual(normalize_msisdn('+255 712 345 678'), '255712345678')
        with self.assertRaises(ValueError):
            normalize_msisdn('55555')

    @override_settings(EVPAY_ENABLED=True, EVPAY_ENVIRONMENT='sandbox', EVPAY_PRODUCTION_CHARGES_ENABLED=False,
                       EVPAY_BASE_URL='https://api.evpay.co', EVPAY_CLIENT_ID='x', EVPAY_CLIENT_SECRET='x',
                       EVPAY_SIG_KEY='x', EVPAY_WEBHOOK_TOKEN='abc', EVPAY_PUBLIC_BASE_URL='https://example.com')
    def test_sandbox_cannot_call_live_api(self):
        with self.assertRaises(EvPayError):
            ensure_settings_ready()


PILOT = dict(
    EVPAY_ENABLED=True,
    EVPAY_ENVIRONMENT='sandbox',
    EVPAY_PRODUCTION_CHARGES_ENABLED=False,
    EVPAY_COMPANY_ID=1,
    EVPAY_BASE_URL='https://sandbox.evpay.co.tz',
    EVPAY_PUBLIC_BASE_URL='https://wifi.example.com',
    EVPAY_CLIENT_ID='example-id', EVPAY_CLIENT_SECRET='never-use',
    EVPAY_SIG_KEY='signing-for-test', EVPAY_WEBHOOK_SECRET='webhook-test-secret',
    EVPAY_WEBHOOK_TOKEN='testing-token',
)


@override_settings(**PILOT)
class EvPayLabTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='EvPay Test Operator')
        self.other_company = Company.objects.create(name='Other Operator')
        # The settings above are fixed to pk=1 for standard isolated test DB.
        self.assertEqual(self.company.pk, 1)
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner-evpay@example.com', password='StrongPassword123!')
        self.other_owner = User.objects.create_user(username='other-evpay@example.com', password='StrongPassword123!')
        Membership.objects.create(user=self.owner, company=self.company, role='OWNER')
        Membership.objects.create(user=self.other_owner, company=self.other_company, role='OWNER')
        self.client.force_login(self.owner)

    def _push(self, phone='255712345678', amount=500):
        with patch('payments.evpay_views.initiate_ussd', return_value={'transactionId': 'E123456'}) as post:
            response = self.client.post(reverse('payments:evpay_start'),
                                        {'operator': 'Mpesa', 'phone': phone, 'amount': amount, 'authorized': 'on'})
        self.assertEqual(response.status_code, 302)
        return EvPayTestPayment.objects.latest('created_at')

    def _webhook(self, obj, event='payment.succeeded', status='SUCCESS', amount=None, delivery='delivery-001', valid=True):
        t = int(time.time())
        body = json.dumps({'event': event, 'timestamp': t, 'data': {
            'orderReference': obj.reference, 'id': 'E123456', 'status': status,
            'amount': amount if amount is not None else int(obj.amount), 'currency': 'TZS',
        }}, separators=(',', ':')).encode('utf-8')
        signature = sign_payload('webhook-test-secret', t, body)
        if not valid:
            signature = '0' * 64
        return self.client.post(reverse('payments:evpay_webhook', kwargs={'token':'testing-token'}),
                                data=body, content_type='application/json',
                                HTTP_X_EVPAY_DELIVERY=delivery, HTTP_X_EVPAY_EVENT=event,
                                HTTP_X_EVPAY_SIGNATURE=f't={t},v1={signature}')

    def test_only_approved_business_owner_can_open_lab(self):
        self.assertEqual(self.client.get(reverse('payments:evpay_lab')).status_code, 200)
        self.client.force_login(self.other_owner)
        self.assertEqual(self.client.get(reverse('payments:evpay_lab')).status_code, 404)

    def test_initiate_is_pending_not_paid(self):
        obj = self._push()
        self.assertEqual(obj.status, 'PENDING')
        self.assertEqual(obj.phone, '255712345678')
        self.assertEqual(PaymentOrder.objects.count(), 0)

    def test_signed_webhook_updates_once(self):
        obj = self._push()
        response = self._webhook(obj)
        self.assertEqual(response.status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'SUCCESS')
        self.assertEqual(EvPayDelivery.objects.count(), 1)
        self.assertEqual(self._webhook(obj).status_code, 200)
        self.assertEqual(EvPayDelivery.objects.count(), 1)
        self.assertEqual(PaymentOrder.objects.count(), 0)

    def test_invalid_signature_and_wrong_amount_cannot_confirm(self):
        obj = self._push()
        self.assertEqual(self._webhook(obj, valid=False).status_code, 401)
        self.assertEqual(self._webhook(obj, amount=999).status_code, 400)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'PENDING')

    def test_settled_not_regressed_by_stale_success(self):
        obj = self._push()
        self.assertEqual(self._webhook(obj, event='payment.settled', status='SETTLED', delivery='del-002').status_code, 200)
        self.assertEqual(self._webhook(obj, delivery='del-003').status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'SETTLED')

    def test_reconciliation_checks_reference(self):
        obj = self._push()
        response_data = {'customReference': obj.reference, 'status': 'SUCCESS', 'amount': 500,
                         'currency': 'TZS', 'type': 'mobile', 'transRef':'E123456'}
        with patch('payments.evpay_views.retrieve_ussd', return_value=response_data):
            response = self.client.post(reverse('payments:evpay_reconcile', args=[obj.pk]))
        self.assertEqual(response.status_code,302)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'SUCCESS')
        self.assertEqual(PaymentOrder.objects.count(), 0)

    def test_reconciliation_mismatch_is_rejected(self):
        obj = self._push()
        with patch('payments.evpay_views.retrieve_ussd', return_value={
            'customReference': 'OTHER-ORDER', 'status': 'SUCCESS', 'amount': 500, 'currency': 'TZS'}):
            self.client.post(reverse('payments:evpay_reconcile', args=[obj.pk]))
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'PENDING')
