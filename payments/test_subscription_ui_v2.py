"""Safe, no-network tests for WorldLink monthly billing UI and exact expiry."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tenants.models import Company, Membership
from payments.models import PlatformSubscriptionPayment
from payments.platform_subscription import apply_subscription_status, next_month_datetime


@override_settings(EVPAY_ENVIRONMENT='live', WORLDLINK_SUBSCRIPTIONS_ENABLED=True,
                   WORLDLINK_SUBSCRIPTIONS_ENFORCED=False)
class SubscriptionUIV2Tests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='RAHA billing test', status='ACTIVE')
        self.owner = get_user_model().objects.create_user(username='r-owner', password='strong-test-pass')
        Membership.objects.create(user=self.owner, company=self.company, role='OWNER')
        self.client.force_login(self.owner)

    def new_payment(self, reference='WLS-V2TEST'): 
        return PlatformSubscriptionPayment.objects.create(
            reference=reference, company=self.company, created_by=self.owner,
            amount=Decimal('20000.00'), currency='TZS', phone='255712345678',
            operator='Mpesa', environment='live', status='PENDING')

    def test_page_price_and_native_select(self):
        response = self.client.get(reverse('payments:subscription_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TZS 20,000')
        self.assertContains(response, 'data-native-select')
        self.assertContains(response, 'wlsubPayButton')

    def test_swahili_checkout(self):
        session = self.client.session
        session['ui_lang'] = 'sw'
        session.save()
        response = self.client.get(reverse('payments:subscription_dashboard'))
        self.assertContains(response, 'Lipa kwa simu')
        self.assertContains(response, 'Chagua mtandao')

    def test_verified_payment_gives_one_exact_calendar_month(self):
        payment = self.new_payment()
        apply_subscription_status(reference=payment.reference, status='SUCCESS',
                                  amount='20000.00', currency='TZS')
        payment.refresh_from_db()
        self.company.refresh_from_db()
        self.assertIsNotNone(payment.period_started_at)
        self.assertEqual(payment.period_expires_at, self.company.subscription_expires_at)
        self.assertEqual(payment.period_expires_at, next_month_datetime(payment.period_started_at))
        first = self.company.subscription_expires_at
        apply_subscription_status(reference=payment.reference, status='SETTLED',
                                  amount='20000.00', currency='TZS')
        self.company.refresh_from_db()
        self.assertEqual(self.company.subscription_expires_at, first)

    def test_pending_does_not_renew(self):
        payment = self.new_payment()
        apply_subscription_status(reference=payment.reference, status='PENDING',
                                  amount='20000.00', currency='TZS')
        self.company.refresh_from_db()
        self.assertIsNone(self.company.subscription_expires_at)

    def test_second_confirmed_payment_extends_existing_period(self):
        p1 = self.new_payment('WLS-V2FIRST')
        apply_subscription_status(reference=p1.reference, status='SUCCESS', amount='20000.00', currency='TZS')
        self.company.refresh_from_db()
        first = self.company.subscription_expires_at
        p2 = self.new_payment('WLS-V2SECOND')
        apply_subscription_status(reference=p2.reference, status='SUCCESS', amount='20000.00', currency='TZS')
        self.company.refresh_from_db()
        self.assertEqual(self.company.subscription_expires_at, next_month_datetime(first))

    def test_staff_can_see_business_expiry(self):
        staff = get_user_model().objects.create_superuser(username='billing-staff', password='strong-test-pass', email='staff@example.test')
        self.client.force_login(staff)
        response = self.client.get(reverse('payments:platform_subscriptions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'RAHA billing test')
        self.assertContains(response, 'Subscription expiry by business')

    def test_business_cannot_open_worldlink_staff_subscriptions(self):
        response = self.client.get(reverse('payments:platform_subscriptions'))
        self.assertEqual(response.status_code, 403)


@override_settings(EVPAY_ENVIRONMENT='live', WORLDLINK_SUBSCRIPTIONS_ENABLED=True,
                   WORLDLINK_SUBSCRIPTIONS_ENFORCED=False, EVPAY_ENABLED=True,
                   EVPAY_PRODUCTION_CHARGES_ENABLED=True)
class SubscriptionFailureStatusTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Failure status test', status='ACTIVE')
        self.owner = get_user_model().objects.create_user(
            username='failure-status-owner', password='strong-test-pass')
        Membership.objects.create(user=self.owner, company=self.company, role='OWNER')
        self.client.force_login(self.owner)

    def new_payment(self, status='UNKNOWN', reference='WLS-FAILED-TEST'):
        return PlatformSubscriptionPayment.objects.create(
            reference=reference, company=self.company, created_by=self.owner,
            amount=Decimal('20000.00'), currency='TZS', phone='255712345678',
            operator='Mpesa', environment='live', status=status)

    def test_cancelled_provider_failure_is_failed_and_localized(self):
        p = self.new_payment()
        apply_subscription_status(reference=p.reference, status='FAILED',
                                  amount='20000.00', currency='TZS',
                                  failure_reason={'code':'CUSTOMER_CANCELLED', 'message':'ignore raw message'})
        p.refresh_from_db()
        self.company.refresh_from_db()
        self.assertEqual(p.status, 'FAILED')
        self.assertEqual(p.last_error, 'EVPAY_FAILURE:CUSTOMER_CANCELLED')
        self.assertIsNone(self.company.subscription_expires_at)
        session = self.client.session
        session['ui_lang'] = 'sw'
        session.save()
        page = self.client.get(reverse('payments:subscription_status',args=[p.pk]))
        self.assertContains(page, 'Umeghairi')
        self.assertContains(page, 'Jaribu kulipa tena')
        state = self.client.get(reverse('payments:subscription_state',args=[p.pk])).json()
        self.assertEqual(state['failure_code'], 'CUSTOMER_CANCELLED')

    def test_unknown_is_not_failed_and_cannot_retry(self):
        p = self.new_payment()
        self.assertContains(self.client.get(reverse('payments:subscription_status',args=[p.pk])),
                            'EvPay could not verify this request')
        with patch('payments.subscription_views.ensure_settings_ready'), \
             patch('payments.subscription_views.charge_subscription') as charge:
            response = self.client.post(reverse('payments:subscription_start'),
                {'phone':'0712345678', 'operator':'Mpesa'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PlatformSubscriptionPayment.objects.filter(company=self.company).count(), 1)
        charge.assert_not_called()

    def test_immediate_provider_failed_not_rewritten_to_pending(self):
        with patch('payments.subscription_views.ensure_settings_ready'), \
             patch('payments.subscription_views.charge_subscription') as charge:
            charge.return_value = {'status':'FAILED', 'amount':20000, 'currency':'TZS',
                                   'failureReason':{'code':'CUSTOMER_CANCELLED'}}
            response = self.client.post(reverse('payments:subscription_start'),
                {'phone':'0712345678', 'operator':'Mpesa'})
        self.assertEqual(response.status_code, 302)
        p=PlatformSubscriptionPayment.objects.get(company=self.company)
        self.assertEqual(p.status, 'FAILED')
        self.assertEqual(p.last_error, 'EVPAY_FAILURE:CUSTOMER_CANCELLED')
        self.assertIsNone(p.applied_at)

    def test_api_outage_stays_unknown_not_failed(self):
        from payments.evpay import EvPayError
        with patch('payments.subscription_views.ensure_settings_ready'), \
             patch('payments.subscription_views.charge_subscription', side_effect=EvPayError('timeout')):
            self.client.post(reverse('payments:subscription_start'),
                             {'phone':'0712345678', 'operator':'Mpesa'})
        self.assertEqual(PlatformSubscriptionPayment.objects.get().status, 'UNKNOWN')


    def test_verified_insufficient_funds_is_translated_and_retryable(self):
        p = self.new_payment(status='PENDING', reference='WLS-INSUFF-TEST')
        apply_subscription_status(
            reference=p.reference, status='FAILED', amount='20000.00', currency='TZS',
            failure_reason={'code':'INSUFFICIENT_FUNDS', 'message':'Do not display raw details'})
        p.refresh_from_db()
        self.company.refresh_from_db()
        self.assertEqual(p.status, 'FAILED')
        self.assertEqual(p.last_error, 'EVPAY_FAILURE:INSUFFICIENT_FUNDS')
        self.assertIsNone(p.applied_at)
        self.assertIsNone(self.company.subscription_expires_at)
        status_url = reverse('payments:subscription_status',args=[p.pk])
        en = self.client.get(status_url)
        self.assertContains(en, 'Insufficient mobile-money balance')
        self.assertContains(en, 'Failed · Insufficient funds')
        self.assertContains(en, 'Try payment again')
        self.assertNotContains(en, 'Do not display raw details')
        self.assertEqual(self.client.get(reverse('payments:subscription_state',args=[p.pk])).json()['failure_code'],
                         'INSUFFICIENT_FUNDS')
        dashboard = self.client.get(reverse('payments:subscription_dashboard'))
        self.assertContains(dashboard, 'Failed · Insufficient funds')
        self.assertContains(dashboard, 'wlsubPayForm')  # payment is terminal, so checkout is available
        session=self.client.session
        session['ui_lang']='sw'
        session.save()
        sw = self.client.get(status_url)
        self.assertContains(sw, 'Hauna salio la kutosha')
        self.assertContains(sw, 'Imeshindikana · Salio halitoshi')
        self.assertContains(sw, 'Jaribu kulipa tena')
        sw_dashboard = self.client.get(reverse('payments:subscription_dashboard'))
        self.assertContains(sw_dashboard, 'Imeshindikana · Salio halitoshi')

    def test_failed_reconciliation_without_reason_preserves_insufficient_code(self):
        p = self.new_payment(status='UNKNOWN', reference='WLS-INSUFF-PRESERVE')
        apply_subscription_status(
            reference=p.reference, status='FAILED', amount='20000.00', currency='TZS',
            failure_reason={'code':'INSUFFICIENT_FUNDS'})
        apply_subscription_status(
            reference=p.reference, status='FAILED', amount='20000.00', currency='TZS',
            failure_reason=None)
        p.refresh_from_db()
        self.assertEqual(p.last_error, 'EVPAY_FAILURE:INSUFFICIENT_FUNDS')

    def test_readonly_reconciliation_reports_insufficient_funds_without_renewal(self):
        from payments.platform_subscription import retrieve_and_apply_subscription
        p = self.new_payment(status='PENDING', reference='WLS-INSUFF-GET')
        data = {'requestId':p.reference,'status':'FAILED','amount':20000,'currency':'TZS',
                'failureReason': {'code':'INSUFFICIENT_FUNDS','source':'fsp'}}
        with patch('payments.platform_subscription.retrieve_ussd', return_value=data):
            retrieve_and_apply_subscription(p)
        p.refresh_from_db()
        self.company.refresh_from_db()
        self.assertEqual(p.status, 'FAILED')
        self.assertEqual(p.last_error, 'EVPAY_FAILURE:INSUFFICIENT_FUNDS')
        self.assertIsNone(self.company.subscription_expires_at)

    def test_generic_failure_does_not_claim_insufficient_funds(self):
        p = self.new_payment(status='PENDING', reference='WLS-NO-REASON')
        apply_subscription_status(reference=p.reference, status='FAILED',
                                  amount='20000.00', currency='TZS', failure_reason=None)
        page = self.client.get(reverse('payments:subscription_status',args=[p.pk]))
        self.assertContains(page, 'EvPay confirmed this payment failed')
        self.assertNotContains(page, 'Insufficient mobile-money balance')
