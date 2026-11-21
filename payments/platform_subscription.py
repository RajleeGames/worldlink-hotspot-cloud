"""WorldLink platform subscriptions: independent from tenant Wi-Fi payments and wallets.

The amount is server-owned and the original EvPay reference is NEVER charged again.
Only a verified signed webhook or authenticated status retrieval can extend access.
"""
import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .evpay import (_request, access_token, normalize_msisdn,
                    ensure_settings_ready, EvPayError, retrieve_ussd)
from .models import PlatformSubscriptionPayment, PlatformSubscriptionDelivery

PRICE = Decimal('20000.00')
EARNING = {'SUCCESS', 'SETTLED'}
ALLOWED = {'PENDING', 'PROCESSING', 'ON-HOLD', 'SUCCESS', 'SETTLED',
           'FAILED', 'REFUNDED', 'REVERSED'}
OPEN = {'CREATED', 'UNKNOWN', 'PENDING', 'PROCESSING', 'ON-HOLD'}


def active_subscription(company, today=None):
    if not getattr(settings, 'WORLDLINK_SUBSCRIPTIONS_ENFORCED', False):
        return True
    today = today or timezone.localdate()
    return bool(company.subscription_ends and company.subscription_ends >= today)


def next_month(day):
    year = day.year + (day.month // 12)
    month = (day.month % 12) + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def subscription_callback_url():
    ensure_settings_ready(require_callback=True)
    token = getattr(settings, 'EVPAY_SUBSCRIPTION_WEBHOOK_TOKEN', '')
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]{30,150}', token):
        raise EvPayError('Secure subscription callback token is missing or invalid.')
    return (settings.EVPAY_PUBLIC_BASE_URL.rstrip('/')
            + '/payments/subscriptions/webhook/' + token + '/')


def charge_subscription(payment):
    """One USSD initiation per persisted reference. This must never be called on retry."""
    if not getattr(settings, 'WORLDLINK_SUBSCRIPTIONS_ENABLED', False):
        raise EvPayError('Platform subscriptions are not yet enabled.')
    if payment.amount != PRICE or payment.currency != 'TZS':
        raise EvPayError('Subscription amount mismatch.')
    if payment.environment != settings.EVPAY_ENVIRONMENT:
        raise EvPayError('Merchant environment mismatch.')
    payload = {
        'fsOperator': payment.operator, 'amount': int(PRICE),
        'product': 'WorldLink Hotspot Cloud monthly subscription',
        'callbackUrl': subscription_callback_url(),
        'payerAccountId': normalize_msisdn(payment.phone),
        'requestId': payment.reference, 'currency': 'TZS',
        'payerName': payment.company.name[:128],
        'narrative': ('WorldLink SaaS subscription ' + payment.reference)[:256],
    }
    return _request('POST', '/api/v1/payment/ussd', payload,
                    token=access_token(), signed=True, idem_key=payment.reference)


def apply_subscription_status(*, reference, status, amount, currency,
                              transaction_id='', fsp_reference='', delivery_id='', event=''):
    """Exactly-once extension; later SETTLED/repeated deliveries cannot add months."""
    from .evpay_lab import EVENT_STATUSES
    status = str(status or '').upper()
    if status not in ALLOWED or (event and EVENT_STATUSES.get(event) != status):
        raise ValueError('Invalid subscription payment status or event.')
    try:
        verified_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Invalid subscription amount.') from None
    if verified_amount != PRICE or currency != 'TZS':
        raise ValueError('Subscription amount/currency mismatch.')
    with transaction.atomic():
        payment = PlatformSubscriptionPayment.objects.select_for_update().get(reference=reference)
        if payment.amount != PRICE or payment.environment != settings.EVPAY_ENVIRONMENT:
            raise ValueError('Subscription merchant or amount mismatch.')
        if delivery_id and PlatformSubscriptionDelivery.objects.filter(delivery_id=delivery_id).exists():
            return payment, False
        old = payment.status
        permitted = (old in OPEN or old == status or
                     (old == 'SUCCESS' and status in {'SETTLED','REFUNDED','REVERSED'}) or
                     (old == 'SETTLED' and status in {'REFUNDED','REVERSED'}))
        fields = []
        applied = False
        if permitted:
            payment.status = status
            payment.last_checked_at = timezone.now()
            fields.extend(['status', 'last_checked_at'])
            if transaction_id:
                payment.transaction_id = str(transaction_id)[:100]
                fields.append('transaction_id')
            if fsp_reference:
                payment.fsp_reference = str(fsp_reference)[:100]
                fields.append('fsp_reference')
            if status in EARNING and not payment.applied_at:
                company = payment.company.__class__.objects.select_for_update().get(pk=payment.company_id)
                today = timezone.localdate()
                starting = max(today, company.subscription_ends or today)
                ending = next_month(starting)
                company.subscription_ends = ending
                company.save(update_fields=['subscription_ends'])
                payment.period_starts, payment.period_ends = starting, ending
                payment.confirmed_at = timezone.now()
                payment.applied_at = timezone.now()
                fields += ['period_starts','period_ends','confirmed_at','applied_at']
                applied = True
            # A reversal is retained for WorldLink refund/revocation review;
            # do not erase later paid periods or silently charge a second time.
            if status in ('REFUNDED', 'REVERSED') and payment.applied_at:
                payment.last_error = 'Refund or reversal requires WorldLink review.'
                fields.append('last_error')
            payment.save(update_fields=list(dict.fromkeys(fields)))
        if delivery_id:
            PlatformSubscriptionDelivery.objects.create(
                payment=payment, delivery_id=delivery_id,
                event=event[:40], status=status)
        return payment, applied


def retrieve_and_apply_subscription(payment):
    """Read-only status verification; no new charge is sent."""
    data = retrieve_ussd(payment.reference)
    returned_ref = (data.get('customReference') or data.get('reference')
                    or data.get('requestId') or data.get('orderReference'))
    if returned_ref != payment.reference:
        raise ValueError('EvPay returned a different subscription reference.')
    return apply_subscription_status(
        reference=payment.reference, status=data.get('status'),
        amount=data.get('amount'), currency=data.get('currency'),
        transaction_id=data.get('transRef') or data.get('transactionId') or data.get('id') or '',
        fsp_reference=data.get('mnoRef') or data.get('fspReference') or '')
