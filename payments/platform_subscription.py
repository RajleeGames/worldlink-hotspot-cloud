"""WorldLink platform subscriptions: independent from tenant Wi-Fi payments and wallets.

The amount is server-owned and the original EvPay reference is NEVER charged again.
Only a verified signed webhook or authenticated status retrieval can extend access.
"""
import calendar
import re
from datetime import date, datetime, time
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

# Canonical failure codes from EvPay's signed payment.failed callback/status API.
# Only code is stored; never trust/show raw provider message or phone/PIN.
KNOWN_FAILURE_CODES = frozenset({
    'CUSTOMER_CANCELLED', 'CUSTOMER_TIMEOUT', 'INSUFFICIENT_FUNDS',
    'INVALID_PIN', 'SESSION_IN_PROGRESS', 'PUSH_REJECTED',
    'LIMIT_EXCEEDED', 'INVALID_MSISDN', 'CUSTOMER_NOT_FOUND',
    'ACCOUNT_BLOCKED', 'DUPLICATE_TRANSACTION', 'NETWORK_ERROR',
    'AUTHENTICATION_ERROR', 'TRANSACTION_DECLINED',
})


def evpay_failure_code(reason):
    """Extract stable EvPay failureReason.code from an authenticated outcome."""
    code = reason.get('code') if isinstance(reason, dict) else reason
    code = str(code or '').strip().upper()
    return code if code in KNOWN_FAILURE_CODES else 'UNSPECIFIED'


def subscription_expiry(company):
    """Exact expiry first; legacy date-only grace ends at the local day's end."""
    expiry = getattr(company, 'subscription_expires_at', None)
    if expiry is not None:
        return expiry
    end_date = company.subscription_ends
    if end_date is None:
        return None
    return timezone.make_aware(datetime.combine(end_date, time(23, 59, 59)), timezone.get_default_timezone())


def active_subscription(company, today=None):
    if not getattr(settings, 'WORLDLINK_SUBSCRIPTIONS_ENFORCED', False):
        return True
    expiry = subscription_expiry(company)
    return bool(expiry and expiry > timezone.now())


def next_month(day):
    year = day.year + (day.month // 12)
    month = (day.month % 12) + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def next_month_datetime(moment):
    """Same Tanzania local clock time, one calendar month later."""
    local = timezone.localtime(moment, timezone.get_default_timezone())
    return datetime.combine(next_month(local.date()), local.timetz(), local.tzinfo)


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
                              transaction_id='', fsp_reference='', delivery_id='', event='', failure_reason=None):
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
            if status == 'FAILED':
                code = evpay_failure_code(failure_reason)
                # An API status check may omit failureReason on a later retry.
                # Do not erase a previously verified specific failure code.
                previous_specific = (payment.last_error.startswith('EVPAY_FAILURE:')
                                     and payment.last_error != 'EVPAY_FAILURE:UNSPECIFIED')
                if code != 'UNSPECIFIED' or not previous_specific:
                    payment.last_error = 'EVPAY_FAILURE:' + code
                    fields.append('last_error')
            if transaction_id:
                payment.transaction_id = str(transaction_id)[:100]
                fields.append('transaction_id')
            if fsp_reference:
                payment.fsp_reference = str(fsp_reference)[:100]
                fields.append('fsp_reference')
            if status in EARNING and not payment.applied_at:
                company = payment.company.__class__.objects.select_for_update().get(pk=payment.company_id)
                now = timezone.now()
                current_expiry = subscription_expiry(company)
                starting = max(now, current_expiry) if current_expiry else now
                ending = next_month_datetime(starting)
                company.subscription_expires_at = ending
                company.subscription_ends = timezone.localtime(ending).date()
                company.save(update_fields=['subscription_expires_at', 'subscription_ends'])
                payment.period_started_at, payment.period_expires_at = starting, ending
                payment.period_starts = timezone.localtime(starting).date()
                payment.period_ends = timezone.localtime(ending).date()
                payment.confirmed_at = now
                payment.applied_at = now
                fields += ['period_started_at', 'period_expires_at', 'period_starts',
                           'period_ends', 'confirmed_at', 'applied_at']
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
        fsp_reference=data.get('mnoRef') or data.get('fspReference') or '',
        failure_reason=data.get('failureReason'))
