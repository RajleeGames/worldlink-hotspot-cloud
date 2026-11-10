from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from tenants.models import Company, Membership
from networks.models import WifiPlan
from payments.models import PaymentMethod, PaymentOrder
from hotspots.models import HotspotSession
from .models import CaptivePortal

User = get_user_model()


class PublicPortalTests(TestCase):
    def setUp(self):
        self.a = Company.objects.create(name='Kilimanjaro WiFi')
        self.b = Company.objects.create(name='Second WiFi')
        self.a_portal = CaptivePortal.objects.create(company=self.a, enabled=True, headline_en='Guest Network Alpha')
        self.b_portal = CaptivePortal.objects.create(company=self.b, enabled=True, headline_en='PRIVATE SECOND NETWORK')
        self.a_plan = WifiPlan.objects.create(company=self.a, name='One hour', duration_minutes=60, price=500)
        self.b_plan = WifiPlan.objects.create(company=self.b, name='PRIVATE SECOND PLAN', duration_minutes=120, price=1200)
        self.a_method = PaymentMethod.objects.create(company=self.a, channel='MPESA', label='Alpha M-Pesa', account_name='Alpha Merchant', account_number='123456', is_active=True)
        self.b_method = PaymentMethod.objects.create(company=self.b, channel='AIRTEL', label='PRIVATE SECOND METHOD', account_name='Other Merchant', account_number='999999', is_active=True)

    def test_public_portal_is_scoped_to_business(self):
        response = self.client.get(reverse('portal:public', args=[self.a.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Guest Network Alpha')
        self.assertContains(response, 'One hour')
        self.assertNotContains(response, 'PRIVATE SECOND PLAN')
        self.assertNotContains(response, 'PRIVATE SECOND NETWORK')
        self.assertEqual(response.context['methods_count'], 1)

    def test_disabled_or_suspended_portal_is_not_public(self):
        self.a_portal.enabled = False
        self.a_portal.save()
        self.assertEqual(self.client.get(reverse('portal:public', args=[self.a.slug])).status_code, 404)
        self.a_portal.enabled = True
        self.a_portal.save()
        self.a.status = 'SUSPENDED'
        self.a.save()
        self.assertEqual(self.client.get(reverse('portal:public', args=[self.a.slug])).status_code, 404)

    def test_checkout_refuses_other_business_package(self):
        url = reverse('portal:checkout', args=[self.a.slug, self.b_plan.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_checkout_refuses_other_business_payment_method(self):
        url = reverse('portal:checkout', args=[self.a.slug, self.a_plan.pk])
        response = self.client.post(url, {'customer_name':'Guest A', 'customer_phone':'0712345678', 'method':self.b_method.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaymentOrder.objects.count(), 0)

    def test_portal_payment_is_pending_not_router_access(self):
        url = reverse('portal:checkout', args=[self.a.slug, self.a_plan.pk])
        response = self.client.post(url, {'customer_name':'Guest A', 'customer_phone':'0712345678', 'method':self.a_method.pk})
        self.assertEqual(response.status_code, 302)
        order = PaymentOrder.objects.get()
        self.assertEqual(order.status, 'PENDING')
        self.assertEqual(order.customer_phone, '255712345678')
        self.assertEqual(order.amount, self.a_plan.price)
        self.assertEqual(HotspotSession.objects.count(), 0)
        receipt = self.client.get(reverse('portal:status', args=[self.a.slug, order.public_id]))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, order.reference)
        self.assertContains(receipt, self.a_method.account_number)
        self.assertEqual(receipt['Cache-Control'], 'private, no-store')
        self.assertEqual(self.client.get(reverse('portal:status', args=[self.b.slug, order.public_id])).status_code, 404)

    def test_portal_settings_restricted_to_business_managers(self):
        owner = User.objects.create_user(username='owner-portal@example.com', password='strongTestPassword!')
        viewer = User.objects.create_user(username='viewer-portal@example.com', password='strongTestPassword!')
        Membership.objects.create(company=self.a, user=owner, role='OWNER')
        Membership.objects.create(company=self.a, user=viewer, role='VIEWER')
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('portal:settings')).status_code, 403)
        self.client.force_login(owner)
        self.assertEqual(self.client.get(reverse('portal:settings')).status_code, 200)
