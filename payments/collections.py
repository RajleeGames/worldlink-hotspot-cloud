"""Tenant-isolated, webhook-verified EvPay customer collections.

These payments always go to WorldLink's configured merchant. Only a confirmed
provider event contributes to displayed earnings; only a separately verified
bank/provider settlement may enter the withdrawable wallet.
"""
import secrets
import time
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .evpay import normalize_msisdn, ensure_settings_ready, EvPayError
from .evpay_lab import EVENT_STATUSES
from .models import EvPayCollection, EvPayCollectionDelivery


EARNING_STATUSES = (EvPayCollection.Status.SUCCESS, EvPayCollection.Status.SETTLED)
TERMINAL = {'FAILED', 'REFUNDED', 'REVERSED'}
OPERATORS = {value for value, _ in EvPayCollection._meta.get_field('operator').choices}


def live_central_routes(company_id):
    """Only staff-approved central APs for the exact tenant may take live sales.

    Router onboarding and an online observation alone NEVER enable charges.
    The operator must also opt in globally and allowlist the company.
    """
    from networks.models import OmadaOnboarding
    if (not settings.EVPAY_MULTITENANT_ENABLED or not settings.OMADA_LIVE_ENABLED
            or not company_collection_allowed(company_id)):
        return OmadaOnboarding.objects.none()
    return OmadaOnboarding.objects.filter(
        router__company_id=company_id, router__family='OMADA',
        connection_mode=OmadaOnboarding.ConnectionMode.CENTRAL,
        status=OmadaOnboarding.Status.REVIEWED, reviewed_by__isnull=False,
        managed_site__company_id=company_id, managed_site__openapi_site_id__gt='',
        live_payments_approved_at__isnull=False, live_payments_approved_by__isnull=False,
    )


def company_collection_allowed(company_id):
    """An audited web decision overrides old .env IDs; no company ID edits needed.

    The old setting remains a migration-compatible fallback for companies not
    yet reviewed in the console. It is never a replacement for router approval.
    """
    from .models import EvPayCompanyAuthorization
    choice = EvPayCompanyAuthorization.objects.filter(company_id=company_id).values_list(
        'enabled', flat=True).first()
    if choice is not None:
        return bool(choice)
    return company_id in settings.EVPAY_COLLECTION_COMPANY_IDS


def approved_payment_route(company_id, ap_mac, ssid):
    """Authorize only the AP/SSID owned by this business, never URL-supplied sites."""
    from .omada import normalize_mac
    try:
        mac = normalize_mac(ap_mac)
    except ValueError:
        return False
    if (settings.OMADA_LIVE_ENABLED and company_id == settings.OMADA_PILOT_COMPANY_ID
            and settings.OMADA_AP_MAC and settings.OMADA_SSID):
        try:
            if normalize_mac(settings.OMADA_AP_MAC) == mac and ssid == settings.OMADA_SSID:
                return True
        except ValueError:
            pass
    return bool(ssid and live_central_routes(company_id).filter(
        ap_mac__iexact=mac, ssid_name=ssid,
    ).exists())


def collection_enabled_for(company):
    ready = bool(settings.EVPAY_ENABLED and settings.EVPAY_PUBLIC_CHECKOUT_ENABLED
        and company_collection_allowed(company.pk)
        and settings.OMADA_LIVE_ENABLED
        and all((settings.OMADA_CONTROLLER_URL, settings.OMADA_CONTROLLER_ID,
                 settings.OMADA_OPERATOR_NAME, settings.OMADA_OPERATOR_PASSWORD))
        and ((company.pk == settings.OMADA_PILOT_COMPANY_ID
              and bool(settings.OMADA_AP_MAC and settings.OMADA_SSID))
             or (company.status == 'ACTIVE' and live_central_routes(company.pk).exists()))
        and settings.EVPAY_COLLECTION_WEBHOOK_TOKEN
        and (settings.EVPAY_ENVIRONMENT != 'live' or settings.WHC_REDIS_URL))
    if not ready:
        return False
    try:
        ensure_settings_ready(require_callback=True)
    except EvPayError:
        return False
    return True


def start_collection(*, company, plan, name, phone, operator, nonce, omada_context):
    """Create once with the database price, never a browser-supplied amount."""
    if not collection_enabled_for(company) or plan.company_id != company.pk or not plan.is_active:
        raise ValueError('Public USSD is not available for this business or package.')
    if operator not in OPERATORS:
        raise ValueError('Choose a supported mobile-money network.')
    phone = normalize_msisdn(phone)
    amount = Decimal(plan.price)
    if amount != amount.to_integral_value() or not 100 <= amount <= settings.EVPAY_PUBLIC_MAX_AMOUNT_TZS:
        raise ValueError('This package is outside the approved live payment limit.')
    if not 2 <= len(name.strip()) <= 90:
        raise ValueError('Enter the customer name.')
    if not omada_context or not approved_payment_route(
            company.pk, omada_context.get('apMac'), omada_context.get('ssidName')):
        raise ValueError('Connect to the WorldLink Wi-Fi first to purchase this package.')
    captured_at = omada_context.get('capturedAt')
    if not isinstance(captured_at, int) or not 0 <= time.time() - captured_at <= 600:
        raise ValueError('Your Wi-Fi login session expired. Reconnect to the hotspot and try again.')
    with transaction.atomic():
        # Client-side retry/double-submit has the same transaction; no second push.
        existing = EvPayCollection.objects.filter(checkout_nonce=nonce).first()
        if existing:
            if existing.company_id != company.pk or existing.plan_id != plan.pk:
                raise ValueError('This checkout request was already used for another order.')
            return existing, False
        collection = EvPayCollection.objects.create(
            company=company, plan=plan, checkout_nonce=nonce,
            reference='WHP-' + secrets.token_hex(10).upper(),
            customer_name=name.strip(), phone=phone, operator=operator,
            amount=amount, environment=settings.EVPAY_ENVIRONMENT,
            client_mac=omada_context['clientMac'], client_ip=omada_context.get('clientIp'),
            ap_mac=omada_context['apMac'], ssid_name=omada_context['ssidName'],
            radio_id=omada_context['radioId'],
        )
        return collection, True


def apply_collection_status(*, reference, status, amount, currency, transaction_id='',
                            fsp_reference='', delivery_id='', event=''):
    """Apply only authenticated callback or trusted server-to-server reconciliation.

    Returns (collection, changed). Concurrent duplicate deliveries are serialized
    using the row lock, and never double-count customer earnings.
    """
    status = str(status or '').upper()
    if status not in {'PENDING', 'PROCESSING', 'ON-HOLD', 'SUCCESS', 'SETTLED', 'FAILED', 'REFUNDED', 'REVERSED'}:
        raise ValueError('Unknown EvPay status.')
    if event and EVENT_STATUSES.get(event) != status:
        raise ValueError('Webhook event/status disagreement.')
    try:
        paid_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Invalid amount.') from None
    with transaction.atomic():
        collection = EvPayCollection.objects.select_for_update().filter(reference=reference).first()
        if collection is None:
            raise LookupError('Unrecognized customer payment reference.')
        if (currency != 'TZS' or paid_amount != collection.amount
                or collection.environment != settings.EVPAY_ENVIRONMENT):
            raise ValueError('Amount, currency or merchant environment does not match.')
        if delivery_id and EvPayCollectionDelivery.objects.filter(delivery_id=delivery_id).exists():
            return collection, False
        current = collection.status
        permitted = (current in ('CREATED', 'UNKNOWN', 'PENDING', 'PROCESSING', 'ON-HOLD') or
                     (current == 'SUCCESS' and status in ('SUCCESS', 'SETTLED', 'REFUNDED', 'REVERSED')) or
                     (current == 'SETTLED' and status in ('SETTLED', 'REFUNDED', 'REVERSED')) or
                     current == status)
        changed = permitted and current != status
        if permitted:
            collection.status = status
            if transaction_id:
                collection.transaction_id = str(transaction_id)[:100]
            if fsp_reference:
                collection.fsp_reference = str(fsp_reference)[:100]
            collection.last_checked_at = timezone.now()
            if status in EARNING_STATUSES and not collection.confirmed_at:
                collection.confirmed_at = timezone.now()
            collection.save(update_fields=['status', 'transaction_id', 'fsp_reference',
                                           'confirmed_at', 'last_checked_at'])
        if delivery_id:
            EvPayCollectionDelivery.objects.create(collection=collection,
                delivery_id=delivery_id, event=event, status=status)
        return collection, changed
