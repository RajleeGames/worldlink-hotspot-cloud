"""Expired guest internet messaging is tenant-scoped and never renews access."""
import time
import uuid
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from networks.models import WifiPlan
from payments.models import EvPayCollection
from tenants.models import Company
from vouchers.models import Voucher, VoucherBatch, VoucherRedemption
from .models import CaptivePortal


class ExpiredGuestPageTests(TestCase):
    def setUp(self):
        self.business = Company.objects.create(name='Kijiji Wi-Fi')
        self.other = Company.objects.create(name='Another hotspot')
        CaptivePortal.objects.create(company=self.business, enabled=True)
        CaptivePortal.objects.create(company=self.other, enabled=True)
        self.plan = WifiPlan.objects.create(company=self.business, name='5 minutes',
                                           duration_minutes=5, price=100)
        self.mac = '12-34-56-78-90-AB'
        self.ap_mac = 'B8-FB-B3-79-B5-60'
        self.context = dict(clientMac=self.mac, clientIp='192.168.1.20',
                            apMac=self.ap_mac, ssidName='KIJIJI-WIFI', radioId=0,
                            capturedAt=int(time.time()))

    def _set_context(self):
        session = self.client.session
        session[f'whc_omada_client_{self.business.pk}'] = self.context
        session.save()

    def _payment(self, confirmed_at):
        return EvPayCollection.objects.create(
            company=self.business, plan=self.plan, checkout_nonce=uuid.uuid4(),
            reference='WHP-' + uuid.uuid4().hex[:20], customer_name='Payer',
            phone='255712345678', operator='Mpesa', amount=100,
            environment='sandbox', status='SUCCESS', confirmed_at=confirmed_at,
            omada_activated_at=confirmed_at + timedelta(seconds=1),
            client_mac=self.mac, ap_mac=self.ap_mac, ssid_name='KIJIJI-WIFI',
        )

    def test_expired_payment_receipt_shows_rebuy_and_swahili(self):
        payment = self._payment(timezone.now() - timedelta(minutes=10))
        url = reverse('portal:evpay_status', args=[self.business.slug, payment.public_id])
        en = self.client.get(url)
        self.assertContains(en, 'Your internet package has expired')
        self.assertContains(en, 'Buy internet again')
        self.assertContains(en, 'data-guest-expiry')
        sw = self.client.get(url + '?lang=sw')
        self.assertContains(sw, 'Muda wa kifurushi chako cha intaneti umeisha')

    def test_running_payment_receipt_has_seconds_countdown(self):
        payment = self._payment(timezone.now() - timedelta(seconds=30))
        response = self.client.get(reverse('portal:evpay_status',
                                           args=[self.business.slug, payment.public_id]))
        self.assertContains(response, 'data-expiry-clock')
        self.assertContains(response, 'data-expiry-renew')
        self.assertNotIn('Your internet package has expired', response.content.decode('utf-8').split('<h1 data-expiry-heading>')[1].split('</h1>')[0])

    def test_expired_message_only_for_same_client_and_business(self):
        self._payment(timezone.now() - timedelta(minutes=10))
        url = reverse('portal:public', args=[self.business.slug])
        self.assertNotContains(self.client.get(url), 'guest-expiry-notice')
        self._set_context()
        self.assertContains(self.client.get(url), 'guest-expiry-notice')
        self.assertNotContains(self.client.get(reverse('portal:public', args=[self.other.slug])),
                               'guest-expiry-notice')
        # A new valid package must suppress the older expired notification.
        self._payment(timezone.now() - timedelta(seconds=30))
        self.assertNotContains(self.client.get(url), 'guest-expiry-notice')

    def test_expired_voucher_receipt_has_rebuy_link(self):
        batch = VoucherBatch.objects.create(company=self.business, plan=self.plan, quantity=1)
        voucher = Voucher.objects.create(company=self.business, batch=batch, code='WHC-TESTEXPIRE')
        redeemed = VoucherRedemption.objects.create(
            voucher=voucher, company=self.business, client_mac=self.mac,
            client_ip='192.168.1.20', ap_mac=self.ap_mac, ssid_name='KIJIJI-WIFI',
            radio_id=0, activated_at=timezone.now() - timedelta(minutes=10),
            expires_at=timezone.now() - timedelta(minutes=5),
        )
        self._set_context()
        url = reverse('portal:voucher_status', args=[self.business.slug, redeemed.public_id])
        response = self.client.get(url)
        self.assertContains(response, 'Your internet package has expired')
        self.assertContains(response, 'Buy internet again')
