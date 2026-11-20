from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from networks.models import WifiPlan
from payments.models import EvPayCollection
from tenants.models import Company, Membership
from vouchers.models import ManualSale, Voucher, VoucherBatch


class VerifiedRevenueReportTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Revenue Shop')
        self.other = Company.objects.create(name='PRIVATE STORE')
        self.owner = get_user_model().objects.create_user(username='revenue', password='test12AA!')
        Membership.objects.create(company=self.company, user=self.owner, role='OWNER')
        self.plan = WifiPlan.objects.create(company=self.company, name='ONE HOUR',
                                            price=100, duration_minutes=60)
        batch = VoucherBatch.objects.create(company=self.company, plan=self.plan,
                                             quantity=1, created_by=self.owner)
        voucher = Voucher.objects.create(company=self.company, batch=batch, code='WHC-REPORT001')
        ManualSale.objects.create(company=self.company, voucher=voucher,
                                  amount=Decimal('100'), method='CASH', recorded_by=self.owner)
        self.paid = self.create_evpay(self.company, self.plan, 'SUCCESS', 200)
        self.create_evpay(self.company, self.plan, 'PENDING', 900)
        foreign_plan = WifiPlan.objects.create(company=self.other, name='PRIVATE PLAN', price=600,
                                               duration_minutes=60)
        self.create_evpay(self.other, foreign_plan, 'SETTLED', 600)
        self.client.force_login(self.owner)

    def create_evpay(self, company, plan, status, amount):
        return EvPayCollection.objects.create(
            company=company, plan=plan, checkout_nonce=uuid4(),
            reference=f'REPORT-{uuid4().hex[:10]}', customer_name='Paying User',
            phone='255710123456', operator='Mpesa', amount=amount,
            environment='live', status=status,
            confirmed_at=timezone.now() if status in ('SUCCESS', 'SETTLED') else None,
        )

    def test_all_contains_only_verified_and_manual_tenant_sales(self):
        response = self.client.get(reverse('cloud:reports'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], Decimal('300'))
        self.assertContains(response, self.paid.reference)
        self.assertNotContains(response, 'PRIVATE PLAN')

    def test_filters_manual_vs_evpay_and_rejects_unknown(self):
        url = reverse('cloud:reports')
        manual = self.client.get(url + '?source=manual')
        self.assertEqual(manual.context['total'], 100)
        self.assertNotContains(manual, self.paid.reference)
        evpay = self.client.get(url + '?source=evpay')
        self.assertEqual(evpay.context['total'], 200)
        self.assertNotContains(evpay, 'WHC-REPORT001')
        invalid = self.client.get(url + '?source=madeup')
        self.assertEqual(invalid.context['source'], 'all')
