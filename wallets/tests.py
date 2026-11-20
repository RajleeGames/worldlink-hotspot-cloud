import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from tenants.models import Company, Membership
from controlcenter.models import PlatformAudit
from .models import BusinessWallet, SettledCollection, WithdrawalDestination, WithdrawalRequest
from .services import (claim_withdrawal, finish_withdrawal, record_settled_collection,
                       request_withdrawal, review_destination, cancel_withdrawal)

User = get_user_model()


class WalletWorkflowTests(TestCase):
    def setUp(self):
        self.a = Company.objects.create(name='Moshi Wi-Fi')
        self.b = Company.objects.create(name='Arusha Wi-Fi')
        self.owner = User.objects.create_user(username='wallet-owner@example.com', password='SecureWalletPassword1!')
        self.other = User.objects.create_user(username='other-wallet@example.com', password='SecureWalletPassword1!')
        self.viewer = User.objects.create_user(username='wallet-viewer@example.com', password='SecureWalletPassword1!')
        self.staff = User.objects.create_user(username='no-finance@example.com', password='SecureWalletPassword1!', is_staff=True)
        self.manager = User.objects.create_superuser(username='worldlink-finance@example.com', password='SecureWalletPassword1!')
        Membership.objects.create(company=self.a, user=self.owner, role='OWNER')
        Membership.objects.create(company=self.b, user=self.other, role='OWNER')
        Membership.objects.create(company=self.a, user=self.viewer, role='VIEWER')
        self.destination = WithdrawalDestination.objects.create(company=self.a, provider='MPESA',
            phone='255712345678', account_name='Miraji Ally', created_by=self.owner)

    def credit(self, amount=10000, ref='REAL-PAY-00001'):
        return record_settled_collection(company=self.a, actor=self.manager, amount=amount,
            source_reference=ref, settlement_reference='BANK-SETTLED-001')

    def verify(self):
        return review_destination(destination=self.destination, actor=self.manager, approve=True,
                                  evidence='Confirmed owner name with provider on 19 Nov')

    def wallet(self):
        return BusinessWallet.objects.get(company=self.a)

    def test_no_test_payment_or_manual_sales_fund_wallet(self):
        from payments.models import EvPayTestPayment
        EvPayTestPayment.objects.create(company=self.a, created_by=self.owner,
            reference='WHT-EXAMPLE-100', operator='Mpesa', phone='255712345678',
            amount=1000, environment='live', status='SETTLED')
        self.assertFalse(BusinessWallet.objects.filter(company=self.a).exists())
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('wallets:dashboard')), '0')
        self.assertFalse(SettledCollection.objects.exists())

    def test_only_platform_manager_can_confirm_real_collections_and_duplicate_is_blocked(self):
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            record_settled_collection(company=self.a, actor=self.owner, amount=1000,
                source_reference='REAL-PAY-00001', settlement_reference='BANK-SETTLED-001')
        self.credit()
        with self.assertRaises(ValueError):
            self.credit()
        balance = self.wallet()
        self.assertEqual(balance.collected, 10000)
        self.assertEqual(balance.available, 10000)
        self.assertEqual(SettledCollection.objects.count(), 1)
        self.assertTrue(PlatformAudit.objects.filter(action='WALLET_COLLECTION_CONFIRMED').exists())
        with self.assertRaises(ValueError):
            self.credit(amount=-10, ref='REAL-PAY-00002')

    def test_owner_isolation_and_no_unauthorized_submission(self):
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('wallets:dashboard')), 'Miraji Ally')
        self.assertEqual(self.client.post(reverse('wallets:withdrawal_cancel', args=[9999])).status_code, 404)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('wallets:dashboard')).status_code, 403)
        self.assertEqual(self.client.get(reverse('wallets:withdrawal_new')).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('wallets:queue')).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('wallets:queue')).status_code, 403)
        self.assertEqual(self.client.post(reverse('wallets:destination_review',args=[self.destination.pk]),
            {'action':'approve','evidence':'Unknown'}).status_code, 403)

    def test_phone_normalizes_but_requires_real_staff_verification(self):
        self.client.force_login(self.owner)
        url = reverse('wallets:destination_add')
        self.assertEqual(self.client.post(url, {'provider':'AIRTEL', 'phone':'0713 456 789',
                'account_name':'Test Customer','password':'incorrect'}).status_code, 200)
        self.assertEqual(WithdrawalDestination.objects.count(), 1)
        self.assertEqual(self.client.post(url, {'provider':'AIRTEL','phone':'0713 456 789',
                'account_name':'Test Customer','password':'SecureWalletPassword1!'}).status_code, 302)
        newly_added = WithdrawalDestination.objects.get(provider='AIRTEL')
        self.assertEqual(newly_added.phone, '255713456789')
        self.assertEqual(newly_added.status, 'PENDING')
        self.credit()
        with self.assertRaises(ValueError):
            request_withdrawal(company=self.a, destination=newly_added, actor=self.owner,
                amount=1000, request_key=uuid.uuid4())
        self.assertEqual(self.wallet().available, 10000)
        with self.assertRaises(ValueError):
            review_destination(destination=newly_added, actor=self.manager, approve=True, evidence='No proof')
        self.assertEqual(newly_added.status, 'PENDING')

    def test_withdrawal_end_to_end_no_api_payout(self):
        self.credit()
        self.verify()
        self.client.force_login(self.owner)
        page = self.client.get(reverse('wallets:withdrawal_new'))
        self.assertEqual(page.status_code, 200)
        key = self.client.session['wallet_request_nonce']
        response = self.client.post(reverse('wallets:withdrawal_new'), {
            'destination': self.destination.pk, 'amount': 3500,
            'password': 'SecureWalletPassword1!', 'request_key': key,
        })
        self.assertEqual(response.status_code, 302)
        withdrawal = WithdrawalRequest.objects.get()
        self.assertEqual(withdrawal.status, 'REQUESTED')
        self.assertEqual(withdrawal.recipient_name, 'Miraji Ally')
        self.assertEqual(self.wallet().available, 6500)
        self.assertEqual(self.wallet().reserved, 3500)
        self.assertEqual(self.client.post(reverse('wallets:withdrawal_new'), {
            'destination': self.destination.pk, 'amount': 3500,
            'password': 'SecureWalletPassword1!', 'request_key': key,
        }).status_code, 200)
        self.assertEqual(WithdrawalRequest.objects.count(), 1)
        self.client.force_login(self.manager)
        queue = self.client.get(reverse('wallets:queue'))
        self.assertContains(queue, self.a.name)
        self.assertContains(queue, self.destination.phone)
        self.assertEqual(self.client.post(reverse('wallets:withdrawal_review',args=[withdrawal.pk]),
            {'action':'paid','payout_reference':'MPESA-TXN-0001'}).status_code,302)
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, 'REQUESTED')
        self.client.post(reverse('wallets:withdrawal_claim', args=[withdrawal.pk]))
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, 'PROCESSING')
        self.assertEqual(self.client.post(reverse('wallets:withdrawal_review',args=[withdrawal.pk]),
            {'action':'paid','payout_reference':'MPESA-TXN-0001'}).status_code,302)
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, 'PAID')
        self.assertEqual(withdrawal.payout_reference, 'MPESA-TXN-0001')
        self.assertEqual(self.wallet().reserved, 0)
        self.assertEqual(self.wallet().available, 6500)
        self.assertEqual(self.wallet().paid_out, 3500)
        self.assertEqual(self.wallet().collected, 10000)
        with self.assertRaises(ValueError):
            finish_withdrawal(withdrawal=withdrawal, actor=self.manager,
                paid=True, reference='MPESA-TXN-0002')

    def test_rejection_releases_reserved_and_prevents_overdraft(self):
        self.credit(5000)
        self.verify()
        item = request_withdrawal(company=self.a, destination=self.destination,
            actor=self.owner, amount=4500, request_key=uuid.uuid4())
        with self.assertRaises(ValueError):
            request_withdrawal(company=self.a, destination=self.destination,
                actor=self.owner, amount=501, request_key=uuid.uuid4())
        self.assertEqual(self.wallet().available, 500)
        claim_withdrawal(withdrawal=item, actor=self.manager)
        self.assertEqual(finish_withdrawal(withdrawal=item, actor=self.manager,
            paid=False, note='Payout request rejected after checking account'), 'REJECTED')
        self.assertEqual(self.wallet().available, 5000)
        self.assertEqual(self.wallet().reserved, 0)
        self.assertEqual(self.wallet().collected, 5000)

    def test_cancel_before_staff_claim_only_and_cross_tenant_denied(self):
        self.credit(5000)
        self.verify()
        item = request_withdrawal(company=self.a, destination=self.destination,
            actor=self.owner, amount=1500, request_key=uuid.uuid4())
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('wallets:withdrawal_cancel',args=[item.pk])).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('wallets:withdrawal_cancel',args=[item.pk])).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, 'CANCELLED')
        self.assertEqual(self.wallet().available, 5000)
        self.assertEqual(self.wallet().reserved, 0)
        with self.assertRaises(ValueError):
            cancel_withdrawal(withdrawal=item, actor=self.owner)
        another = request_withdrawal(company=self.a, destination=self.destination,
            actor=self.owner, amount=1000, request_key=uuid.uuid4())
        claim_withdrawal(withdrawal=another, actor=self.manager)
        with self.assertRaises(ValueError):
            cancel_withdrawal(withdrawal=another, actor=self.owner)
        self.assertEqual(self.wallet().reserved, 1000)

    def test_worldlink_review_routes_and_number_evidence(self):
        self.client.force_login(self.manager)
        url = reverse('wallets:destination_review', args=[self.destination.pk])
        self.client.post(url, {'action':'approve', 'evidence':'Checked registered account name via trusted provider'})
        self.destination.refresh_from_db()
        self.assertEqual(self.destination.status, 'VERIFIED')
        self.assertEqual(self.destination.verified_by, self.manager)
        self.client.post(url, {'action':'reject', 'evidence':'Changed after first approval'})
        self.destination.refresh_from_db()
        self.assertEqual(self.destination.status, 'VERIFIED')
        collection_url = reverse('wallets:collection_new')
        self.assertEqual(self.client.post(collection_url, {
            'company_id':self.a.pk,'amount':700,'source_reference':'MNO-LIVE-0003',
            'settlement_reference':'WORLDLINK-BANK-0003',
        }).status_code, 302)
        self.assertEqual(self.wallet().available, 700)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(collection_url).status_code, 403)
        self.assertEqual(self.client.get(reverse('wallets:withdrawal_detail',args=[1])).status_code, 403)

    def test_rejected_number_can_be_corrected_without_losing_audit_history(self):
        review_destination(destination=self.destination, actor=self.manager,
            approve=False, evidence='Provider reported registered name differs')
        self.client.force_login(self.owner)
        resp = self.client.post(reverse('wallets:destination_add'), {
            'provider':'MPESA', 'phone':'0712 345 678',
            'account_name':'Correct Registered Name', 'password':'SecureWalletPassword1!',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(WithdrawalDestination.objects.filter(company=self.a).count(), 2)
        self.assertEqual(WithdrawalDestination.objects.filter(status='PENDING').count(), 1)
        self.assertEqual(WithdrawalDestination.objects.filter(status='REJECTED').count(), 1)
