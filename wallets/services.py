"""Manual WorldLink disbursement workflow. NEVER calls EvPay's payout API."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from controlcenter.auth import platform_can_manage
from controlcenter.models import PlatformAudit
from .models import BusinessWallet, SettledCollection, WithdrawalDestination, WithdrawalRequest


def positive_tzs(amount):
    try:
        amount = Decimal(str(amount))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError('Enter a valid amount.') from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal('9999999999999') or amount != amount.to_integral_value():
        raise ValueError('Enter a positive whole-shilling amount.')
    return amount


def _require_platform_manager(actor):
    if not platform_can_manage(actor):
        raise PermissionDenied('WorldLink finance manager access required.')


def wallet_for(company):
    wallet, _ = BusinessWallet.objects.get_or_create(company=company)
    return wallet


@transaction.atomic
def record_settled_collection(*, company, actor, amount, source_reference, settlement_reference):
    """Call ONLY after verifying real cleared funds for a production customer payment.

    This is the integration point for a future authenticated production checkout.
    EvPayTestPayment/PaymentOrder/ManualSale MUST NEVER call it implicitly.
    """
    _require_platform_manager(actor)
    amount = positive_tzs(amount)
    source_reference = source_reference.strip().upper()
    settlement_reference = settlement_reference.strip().upper()
    if not 6 <= len(source_reference) <= 100 or not 6 <= len(settlement_reference) <= 100:
        raise ValueError('Provide the real payment ID and independent settlement/statement reference.')
    if SettledCollection.objects.filter(source_reference=source_reference).exists():
        raise ValueError('This payment was already credited. Check its existing record.')
    wallet = wallet_for(company)
    wallet = BusinessWallet.objects.select_for_update().get(pk=wallet.pk)
    # DB-level unique source reference also protects concurrent workers/retries.
    collection = SettledCollection.objects.create(wallet=wallet, amount=amount,
        source_reference=source_reference, settlement_reference=settlement_reference, confirmed_by=actor)
    BusinessWallet.objects.filter(pk=wallet.pk).update(collected=F('collected') + amount, available=F('available') + amount)
    PlatformAudit.objects.create(actor=actor, company=company, action='WALLET_COLLECTION_CONFIRMED',
        note=f'TZS {amount} · collection #{collection.pk} · settlement evidence on file.')
    return collection


@transaction.atomic
def review_destination(*, destination, actor, approve, evidence):
    _require_platform_manager(actor)
    evidence = evidence.strip()
    if len(evidence) < 10:
        raise ValueError('Record the independent number/name verification or rejection reason (at least 10 characters).')
    destination = WithdrawalDestination.objects.select_for_update().get(pk=destination.pk)
    if destination.status != WithdrawalDestination.Status.PENDING:
        raise ValueError('This destination has already been reviewed.')
    status = WithdrawalDestination.Status.VERIFIED if approve else WithdrawalDestination.Status.REJECTED
    changed = WithdrawalDestination.objects.filter(pk=destination.pk, status='PENDING').update(
        status=status, verified_by=actor, verification_note=evidence[:250], reviewed_at=timezone.now())
    if not changed:
        raise ValueError('This destination has already been reviewed.')
    PlatformAudit.objects.create(actor=actor, company=destination.company,
        action='WITHDRAW_NUMBER_' + status,
        note=f'Destination #{destination.pk} ({destination.provider}) reviewed. Evidence kept in restricted record.')
    return status


@transaction.atomic
def request_withdrawal(*, company, destination, actor, amount, request_key):
    amount = positive_tzs(amount)
    # Read status fresh to avoid a stale form submitting an unverified number.
    if not WithdrawalDestination.objects.filter(pk=destination.pk, company=company, status='VERIFIED').exists():
        raise ValueError('Select a verified payout number belonging to this business.')
    wallet = wallet_for(company)
    # A conditional SQL update avoids two simultaneous requests overdrawing a balance.
    changed = BusinessWallet.objects.filter(pk=wallet.pk, available__gte=amount).update(
        available=F('available') - amount, reserved=F('reserved') + amount)
    if not changed:
        raise ValueError('Insufficient available balance.')
    item = WithdrawalRequest.objects.create(company=company, destination=destination,
        recipient_phone=destination.phone, recipient_name=destination.account_name,
        requested_by=actor, amount=amount, request_key=request_key)
    PlatformAudit.objects.create(actor=actor, company=company, action='WITHDRAW_REQUESTED',
        note=f'Withdrawal #{item.pk}: TZS {amount} reserved for manual payout.')
    return item


@transaction.atomic
def claim_withdrawal(*, withdrawal, actor):
    """Lock the request against owner cancellation before initiating any external transfer."""
    _require_platform_manager(actor)
    changed = WithdrawalRequest.objects.filter(pk=withdrawal.pk, status='REQUESTED').update(
        status=WithdrawalRequest.Status.PROCESSING, processed_by=actor)
    if not changed:
        raise ValueError('Withdrawal already claimed, paid, cancelled or rejected.')
    PlatformAudit.objects.create(actor=actor, company=withdrawal.company,
        action='WITHDRAW_PROCESSING', note=f'Withdrawal #{withdrawal.pk} claimed for external transfer.')


@transaction.atomic
def finish_withdrawal(*, withdrawal, actor, paid, reference='', note=''):
    """Staff must send and verify the transfer OFFLINE before calling paid=True."""
    _require_platform_manager(actor)
    withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal.pk)
    if withdrawal.status != WithdrawalRequest.Status.PROCESSING:
        raise ValueError('Claim this withdrawal for payment first; it may already be closed.')
    reference = reference.strip().upper()
    note = note.strip()
    if paid and len(reference) < 6:
        raise ValueError('Enter the real mobile-money transfer reference after sending the payment.')
    if not paid and len(note) < 10:
        raise ValueError('Explain why this withdrawal was rejected (at least 10 characters).')
    status = WithdrawalRequest.Status.PAID if paid else WithdrawalRequest.Status.REJECTED
    changed = WithdrawalRequest.objects.filter(pk=withdrawal.pk, status='PROCESSING').update(
        status=status, processed_by=actor, processed_at=timezone.now(),
        payout_reference=reference if paid else None, processing_note=note[:250])
    if not changed:
        raise ValueError('This withdrawal has already been processed.')
    updates = {'reserved': F('reserved') - withdrawal.amount}
    if paid:
        updates['paid_out'] = F('paid_out') + withdrawal.amount
    else:
        updates['available'] = F('available') + withdrawal.amount
    updated = BusinessWallet.objects.filter(company=withdrawal.company, reserved__gte=withdrawal.amount).update(**updates)
    if not updated:
        raise ValueError('Wallet reserve mismatch. No status changed.')
    PlatformAudit.objects.create(actor=actor, company=withdrawal.company,
        action='WITHDRAW_' + status, note=f'Withdrawal #{withdrawal.pk} TZS {withdrawal.amount}; {"external payment confirmed" if paid else "funds released"}.')
    return status


@transaction.atomic
def cancel_withdrawal(*, withdrawal, actor):
    withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal.pk)
    if withdrawal.requested_by_id != actor.pk:
        raise PermissionDenied('Only the requesting owner can cancel.')
    changed = WithdrawalRequest.objects.filter(pk=withdrawal.pk, status='REQUESTED').update(
        status=WithdrawalRequest.Status.CANCELLED, processed_at=timezone.now(), processing_note='Cancelled by requester')
    if not changed:
        raise ValueError('This withdrawal is no longer awaiting payment.')
    updated = BusinessWallet.objects.filter(company=withdrawal.company, reserved__gte=withdrawal.amount).update(
        reserved=F('reserved') - withdrawal.amount, available=F('available') + withdrawal.amount)
    if not updated:
        raise ValueError('Wallet reserve mismatch. No status changed.')
    PlatformAudit.objects.create(actor=actor, company=withdrawal.company, action='WITHDRAW_CANCELLED',
        note=f'Withdrawal #{withdrawal.pk}: reserved funds released.')
