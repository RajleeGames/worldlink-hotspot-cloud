"""Safe, no-network tests for WorldLink monthly billing UI and exact expiry."""
from datetime import timedelta
from decimal import Decimal

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
