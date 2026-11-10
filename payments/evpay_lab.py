"""Isolated EvPay test ledger; this does not grant Wi-Fi access."""
import secrets
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .evpay import EvPayError
from .models import EvPayTestPayment, EvPayDelivery

EVENT_STATUSES = {
    'payment.succeeded': 'SUCCESS', 'payment.settled': 'SETTLED',
    'payment.failed': 'FAILED', 'payment.on_hold': 'ON-HOLD',
    'payment.refunded': 'REFUNDED', 'payment.reversed': 'REVERSED',
}
FINAL = {'FAILED', 'REFUNDED', 'REVERSED', 'SETTLED'}


def new_test(*, company, user, operator, phone, amount):
    return EvPayTestPayment.objects.create(
        company=company, created_by=user, operator=operator, phone=phone,
        amount=amount, reference='WHT-' + secrets.token_hex(9).upper(),
        environment=settings.EVPAY_ENVIRONMENT,
    )


def apply_status(*, reference, status, amount, currency, transaction_id='', fsp_reference='', source='POLL', delivery_id='', event=''):
    """Validate known payment/merchant, prevent stale event regressions. Atomic & idempotent."""
    status = (status or '').upper()
    if status not in {'PENDING', 'PROCESSING', 'SUCCESS', 'SETTLED', 'ON-HOLD', 'FAILED', 'REFUNDED', 'REVERSED'}:
        raise ValueError('Unknown EvPay status')
    with transaction.atomic():
        obj = EvPayTestPayment.objects.select_for_update().filter(reference=reference, company_id=settings.EVPAY_COMPANY_ID).first()
        if obj is None:
            raise LookupError('No matching test reference')
        try:
            amount_matches = Decimal(str(amount)) == obj.amount
        except (InvalidOperation, TypeError):
            amount_matches = False
        if currency != 'TZS' or not amount_matches:
            raise ValueError('Amount or currency does not match the original test')
        if delivery_id and EvPayDelivery.objects.filter(delivery_id=delivery_id).exists():
            return obj, False
        # Never regress a terminal result based on an out-of-order retry.
        current = obj.status
        permitted = current in ('CREATED', 'UNKNOWN', 'PENDING', 'PROCESSING', 'ON-HOLD') or (
            current == 'SUCCESS' and status in ('SUCCESS', 'SETTLED', 'REFUNDED', 'REVERSED')
        ) or (current == 'SETTLED' and status in ('SETTLED', 'REVERSED', 'REFUNDED')) or current == status
        if permitted:
            obj.status = status
            if transaction_id:
                obj.transaction_id = str(transaction_id)[:100]
            if fsp_reference:
                obj.fsp_reference = str(fsp_reference)[:100]
            obj.last_checked_at = timezone.now()
            obj.save(update_fields=['status', 'transaction_id', 'fsp_reference', 'last_checked_at'])
        if delivery_id:
            EvPayDelivery.objects.create(payment=obj, delivery_id=delivery_id[:100], event=event[:40], status=status)
        return obj, permitted
