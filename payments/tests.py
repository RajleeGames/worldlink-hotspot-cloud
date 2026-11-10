from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from tenants.models import Company, Membership
from networks.models import WifiPlan
from .models import PaymentMethod, PaymentOrder, PaymentAudit
from .services import create_pending_order, update_order_status

User = get_user_model()


class PaymentIsolationTests(TestCase):
    def setUp(self):
        self.a = Company.objects.create(name='Payments Operator A')
        self.b = Company.objects.create(name='Payments Operator B')
        self.owner_a = User.objects.create_user(username='owner-pay-a@example.com', password='StrongPass1!')
        self.owner_b = User.objects.create_user(username='owner-pay-b@example.com', password='StrongPass1!')
        self.viewer = User.objects.create_user(username='viewer-pay@example.com', password='StrongPass1!')
        Membership.objects.create(company=self.a, user=self.owner_a, role='OWNER')
        Membership.objects.create(company=self.b, user=self.owner_b, role='OWNER')
        Membership.objects.create(company=self.a, user=self.viewer, role='VIEWER')
        self.plan_a = WifiPlan.objects.create(company=self.a, name='Small Plan', duration_minutes=60, price=500)
        self.plan_b = WifiPlan.objects.create(company=self.b, name='Secret Plan', duration_minutes=30, price=1000)
        self.method_a = PaymentMethod.objects.create(company=self.a, channel='CASH', label='Cash desk', is_active=True)
        self.method_b = PaymentMethod.objects.create(company=self.b, channel='CASH', label='Other cash', is_active=True)
        self.order = create_pending_order(company=self.a, plan=self.plan_a, method=self.method_a, name='Guest', phone='255712345678')

    def test_no_cross_tenant_order_access(self):
        self.client.force_login(self.owner_b)
        self.assertEqual(self.client.get(reverse('payments:order_detail',args=[self.order.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse('payments:orders')), self.order.reference)
        self.assertEqual(self.client.post(reverse('payments:verify',args=[self.order.pk]), {'merchant_reference':'TX1234'}).status_code,404)

    def test_no_cross_tenant_method_edit(self):
        self.client.force_login(self.owner_a)
        self.assertEqual(self.client.get(reverse('payments:method_edit',args=[self.method_b.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('payments:method_disable', args=[self.method_b.pk])).status_code,404)

    def test_viewer_cannot_verify(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('payments:orders')).status_code,200)
        self.assertEqual(self.client.post(reverse('payments:verify',args=[self.order.pk]),{'merchant_reference':'TX1234'}).status_code,403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status,'PENDING')

    def test_verified_once_and_requires_statement_reference(self):
        self.client.force_login(self.owner_a)
        path = reverse('payments:verify',args=[self.order.pk])
        self.client.post(path, {'merchant_reference':''})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status,'PENDING')
        self.client.post(path, {'merchant_reference':'Receipt 11122'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status,'PAID')
        self.assertEqual(self.order.merchant_reference,'Receipt 11122')
        self.assertEqual(self.order.verified_by,self.owner_a)
        self.client.post(path, {'merchant_reference':'Receipt 11122'})
        self.assertEqual(PaymentAudit.objects.filter(order=self.order, action='PAID').count(),1)
        self.assertEqual(PaymentOrder.objects.count(),1)

    def test_prevent_cross_business_payment_order_creation(self):
        with self.assertRaises(ValueError):
            create_pending_order(company=self.a, plan=self.plan_b, method=self.method_a, name='Guest', phone='255712345678')
        with self.assertRaises(ValueError):
            create_pending_order(company=self.a, plan=self.plan_a, method=self.method_b, name='Guest', phone='255712345678')

    def test_platform_staff_can_view_but_not_verify_payments(self):
        staff = User.objects.create_superuser(username='worldlink-platform@example.com', email='worldlink-platform@example.com', password='StrongPass1!')
        self.client.force_login(staff)
        response = self.client.get(reverse('controlcenter:platform_payments'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response, self.order.reference)
        self.assertEqual(self.client.post(reverse('payments:verify',args=[self.order.pk]),{'merchant_reference':'TX1234'}).status_code,302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status,'PENDING')

    def test_cannot_reverse_paid_with_cancel(self):
        self.assertTrue(update_order_status(order=self.order,actor=self.owner_a,status='PAID',merchant_reference='TX123',note='cleared'))
        self.assertFalse(update_order_status(order=self.order,actor=self.owner_a,status='CANCELLED'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status,'PAID')
