"""Bilingual business renewals plus strictly signed EvPay platform callbacks."""
import json
import re
import secrets
from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from controlcenter.auth import platform_required
from tenants.models import Company
from tenants.utils import active_membership
from .evpay import normalize_msisdn, ensure_settings_ready, EvPayError, verify_webhook
from .evpay_lab import EVENT_STATUSES
from .models import PlatformSubscriptionPayment
from .platform_subscription import (PRICE, OPEN, active_subscription,
    apply_subscription_status, charge_subscription, retrieve_and_apply_subscription, subscription_expiry)


def _membership(request):
    member = active_membership(request)
    if member is None:
        raise PermissionDenied('A business membership is required.')
    return member


def subscription_view_data(company, *, has_paid=False):
    now = timezone.now()
    expires = subscription_expiry(company)
    future = bool(expires and expires > now)
    days = max(0, ceil((expires - now).total_seconds() / 86400)) if expires else None
    if future and has_paid:
        status = 'expiring' if days <= 7 else 'active'
    elif not has_paid and not getattr(settings, 'WORLDLINK_SUBSCRIPTIONS_ENFORCED', False):
        status = 'grace'
    else:
        status = 'expired'
    return {'expires_at':expires, 'expiry_future':future,
            'expiry_passed': bool(expires and not future), 'days_remaining': days,
            'subscription_status':status}


@login_required
def subscription_dashboard(request):
    m = _membership(request)
    history = PlatformSubscriptionPayment.objects.filter(company=m.company).order_by('-created_at')[:15]
    pending = PlatformSubscriptionPayment.objects.filter(
        company=m.company, status__in=OPEN).order_by('-created_at').first()
    has_paid = PlatformSubscriptionPayment.objects.filter(company=m.company, applied_at__isnull=False).exists()
    response = render(request, 'payments/subscription_dashboard.html', {
        'page_title': 'Monthly subscription', 'company': m.company,
        'price': PRICE, 'fee_display': f'{PRICE:,.0f}', 'history': history, 'pending': pending,
        **subscription_view_data(m.company, has_paid=has_paid),
        'can_pay': m.role in ('OWNER','MANAGER'),
        'can_use': active_subscription(m.company),
        'billing_enabled': getattr(settings, 'WORLDLINK_SUBSCRIPTIONS_ENABLED', False),
    })
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_POST
def subscription_start(request):
    m = _membership(request)
    if m.role not in ('OWNER','MANAGER'):
        raise PermissionDenied('Business owner or manager required.')
    if m.company.status == Company.Status.SUSPENDED:
        messages.error(request, 'Contact WorldLink to resolve your suspended business account.')
        return redirect('payments:subscription_dashboard')
    if not getattr(settings, 'WORLDLINK_SUBSCRIPTIONS_ENABLED', False):
        messages.error(request, 'Subscription payment is temporarily unavailable.')
        return redirect('payments:subscription_dashboard')
    if not settings.EVPAY_ENABLED or not settings.EVPAY_PRODUCTION_CHARGES_ENABLED:
        messages.error(request, 'The WorldLink payment gateway is not ready.')
        return redirect('payments:subscription_dashboard')
    operator = request.POST.get('operator', '')
    allowed = {key for key, _ in PlatformSubscriptionPayment._meta.get_field('operator').choices}
    if operator not in allowed:
        messages.error(request, 'Select your mobile-money network.')
        return redirect('payments:subscription_dashboard')
    try:
        phone = normalize_msisdn(request.POST.get('phone',''))
        ensure_settings_ready(require_callback=True)
    except (ValueError, EvPayError):
        messages.error(request, 'Check the payment details or contact WorldLink support.')
        return redirect('payments:subscription_dashboard')
    # Lock this business so simultaneous taps cannot create two USSD pushes.
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=m.company_id)
        existing = PlatformSubscriptionPayment.objects.filter(
            company=company, status__in=OPEN).order_by('-created_at').first()
        if existing:
            return redirect('payments:subscription_status', pk=existing.pk)
        payment = PlatformSubscriptionPayment.objects.create(
            company=company, created_by=request.user,
            reference='WLS-' + secrets.token_hex(10).upper(),
            phone=phone, operator=operator, amount=PRICE,
            environment=settings.EVPAY_ENVIRONMENT,
        )
    # A failed/ambiguous network response is NOT permission to resend a charge.
    try:
        data = charge_subscription(payment)
        payment.status = 'PENDING' if data.get('status') not in ('PROCESSING',) else 'PROCESSING'
    except EvPayError:
        payment.status = 'UNKNOWN'
        payment.last_error = 'Provider response uncertain. Checking the same reference.'
    # A fast signed webhook can arrive before the initiating API response returns.
    # Never overwrite an already-confirmed or terminal status with PENDING.
    with transaction.atomic():
        current = PlatformSubscriptionPayment.objects.select_for_update().get(pk=payment.pk)
        if current.status in OPEN and not current.applied_at:
            current.status = payment.status
            current.last_error = payment.last_error
            current.save(update_fields=['status', 'last_error'])
    return redirect('payments:subscription_status', pk=payment.pk)


@login_required
def subscription_status(request, pk):
    m = _membership(request)
    p = get_object_or_404(PlatformSubscriptionPayment, pk=pk, company=m.company)
    response = render(request, 'payments/subscription_status.html', {
        'page_title': 'Subscription payment', 'payment': p,
        'active': active_subscription(m.company), 'company': m.company,
    })
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
def subscription_state(request, pk):
    m = _membership(request)
    p = get_object_or_404(PlatformSubscriptionPayment, pk=pk, company=m.company)
    response = JsonResponse({'status':p.status, 'confirmed':bool(p.applied_at),
        'expires':p.period_ends.isoformat() if p.period_ends else None,
        'expires_at':p.period_expires_at.isoformat() if p.period_expires_at else None})
    response['Cache-Control'] = 'no-store'
    return response


@csrf_exempt
@require_POST
def subscription_webhook(request, token):
    secret = settings.EVPAY_WEBHOOK_SECRET
    expected = getattr(settings, 'EVPAY_SUBSCRIPTION_WEBHOOK_TOKEN', '')
    if not expected or not secret or not secrets.compare_digest(token, expected):
        return JsonResponse({'error':'Unauthorized'}, status=401)
    raw = request.body
    if len(raw) > 200000 or not verify_webhook(
            raw, request.headers.get('X-EvPay-Signature',''), secret):
        return JsonResponse({'error':'Invalid signature'}, status=401)
    delivery_id = request.headers.get('X-EvPay-Delivery','')
    event_header = request.headers.get('X-EvPay-Event','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', delivery_id):
        return JsonResponse({'error':'Invalid delivery'}, status=400)
    try:
        obj = json.loads(raw)
        event = obj['event']
        data = obj['data']
        signed_time = int(dict(x.strip().split('=',1) for x in
            request.headers['X-EvPay-Signature'].split(',') if '=' in x)['t'])
        if (not isinstance(data,dict) or obj.get('timestamp') != signed_time
                or event != event_header or event not in EVENT_STATUSES
                or str(data.get('status','')).upper() != EVENT_STATUSES[event]):
            raise ValueError('Mismatch')
        apply_subscription_status(
            reference=data['orderReference'], status=data['status'],
            amount=data['amount'], currency=data['currency'],
            transaction_id=data.get('id') or '',
            fsp_reference=data.get('fspReference') or '',
            delivery_id=delivery_id, event=event)
    except (KeyError, ValueError, TypeError, LookupError, PlatformSubscriptionPayment.DoesNotExist):
        return JsonResponse({'error':'Invalid subscription event'}, status=400)
    response = JsonResponse({'status':'OK'})
    response['Cache-Control'] = 'no-store'
    return response


@platform_required()
def platform_subscriptions(request):
    qs = PlatformSubscriptionPayment.objects.select_related('company').order_by('-created_at')
    paid_company_ids = set(PlatformSubscriptionPayment.objects.filter(
        applied_at__isnull=False).values_list('company_id', flat=True))
    business_rows = []
    for company in Company.objects.order_by('name', 'id'):
        info = subscription_view_data(company, has_paid=company.pk in paid_company_ids)
        business_rows.append({'company':company, 'status':info['subscription_status'],
                              'expires_at':info['expires_at'], 'days_left':info['days_remaining'],
                              'future':info['expiry_future']})
    return render(request,'payments/platform_subscriptions.html',{
        'page_title':'WorldLink subscriptions', 'payments':qs[:200],
        'total_confirmed':qs.filter(status__in=['SUCCESS','SETTLED']).count(),
        'business_count':len(business_rows), 'business_rows':business_rows,
        'active_count':sum(r['status']=='active' for r in business_rows),
        'expiring_count':sum(r['status']=='expiring' for r in business_rows),
        'unpaid_count':sum(r['status'] in ('expired','grace') for r in business_rows),
    })
