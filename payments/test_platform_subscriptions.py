from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tenants.models import Company, Membership
from payments.models import PlatformSubscriptionPayment
from payments.platform_subscription import apply_subscription_status, active_subscription


@override_settings(EVPAY_ENVIRONMENT='live')
class SubscriptionLedgerTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Sub Test', status='ACTIVE')
        self.user = get_user_model().objects.create_user(username='sub-owner', password='strong_pass_test')
        Membership.objects.create(company=self.company, user=self.user, role='OWNER')
        self.payment = PlatformSubscriptionPayment.objects.create(
            company=self.company, created_by=self.user, reference='WLS-UNITTEST01',
            amount=Decimal('20000.00'), currency='TZS', phone='255712345678',
            operator='Mpesa', status='PENDING', environment='live')

    def apply(self, status='SUCCESS', **kwargs):
        return apply_subscription_status(
            reference=self.payment.reference, status=status,
            amount='20000.00', currency='TZS', **kwargs)

    def test_pending_does_not_extend(self):
        self.apply('PENDING')
        self.company.refresh_from_db()
        self.assertIsNone(self.company.subscription_ends)

    def test_success_and_settled_extend_only_once(self):
        payment, credited = self.apply('SUCCESS', delivery_id='delivery-1', event='payment.succeeded')
        self.assertTrue(credited)
        self.company.refresh_from_db()
        first = self.company.subscription_ends
        self.assertIsNotNone(first)
        self.apply('SUCCESS', delivery_id='delivery-1', event='payment.succeeded')
        self.apply('SETTLED', delivery_id='delivery-2', event='payment.settled')
        self.company.refresh_from_db()
        self.assertEqual(self.company.subscription_ends, first)

    def test_tampered_amount_never_extends(self):
        with self.assertRaises(ValueError):
            apply_subscription_status(reference=self.payment.reference,
                status='SUCCESS', amount='100.00', currency='TZS')
        self.company.refresh_from_db()
        self.assertIsNone(self.company.subscription_ends)

    def test_repeated_payment_references_do_not_extend_after_success(self):
        self.apply('SUCCESS')
        self.company.refresh_from_db()
        earlier = self.company.subscription_ends
        self.apply('SUCCESS')
        self.company.refresh_from_db()
        self.assertEqual(earlier, self.company.subscription_ends)

    @override_settings(WORLDLINK_SUBSCRIPTIONS_ENFORCED=True)
    def test_expired_business_redirects_to_billing(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('cloud:dashboard'))
        self.assertRedirects(response, reverse('payments:subscription_dashboard'))

    @override_settings(WORLDLINK_SUBSCRIPTIONS_ENFORCED=False)
    def test_enforcement_off_preserves_old_workspaces(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('cloud:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_other_company_cannot_view_subscription(self):
        other = Company.objects.create(name='Other company', status='ACTIVE')
        other_user = get_user_model().objects.create_user(username='other-owner',password='strong_pass_test')
        Membership.objects.create(company=other,user=other_user,role='OWNER')
        self.client.force_login(other_user)
        response = self.client.get(reverse('payments:subscription_status',args=[self.payment.pk]))
        self.assertEqual(response.status_code,404)
