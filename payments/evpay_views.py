"""Staff-only pilot UI and signed EvPay webhook endpoint."""
import json
import re
import secrets
import hashlib

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db import IntegrityError
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tenants.utils import require_tenant
from .evpay import EvPayError, access_token, initiate_ussd, retrieve_ussd, pilot_enabled_for, verify_webhook, normalize_msisdn
from .evpay_lab import new_test, apply_status, EVENT_STATUSES
from .forms import EvPayTestForm
from .models import EvPayTestPayment


def _ensure_pilot(request):
    if not pilot_enabled_for(request.active_company):
        raise Http404('EvPay pilot is not enabled for this business.')


@require_tenant('OWNER', 'MANAGER')
def lab(request):
    _ensure_pilot(request)
    form = EvPayTestForm()
    qs = EvPayTestPayment.objects.filter(company=request.active_company).select_related('created_by')[:50]
    return render(request, 'payments/evpay_lab.html', {
        'form': form, 'tests': qs, 'environment': settings.EVPAY_ENVIRONMENT,
        'live_locked': settings.EVPAY_ENVIRONMENT != 'sandbox' and not settings.EVPAY_PRODUCTION_CHARGES_ENABLED,
        'page_title': 'EvPay test lab',
    })


@require_tenant('OWNER', 'MANAGER')
@require_POST
def test_auth(request):
    _ensure_pilot(request)
    try:
        access_token()
    except EvPayError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'EvPay API authentication successful. No payment was initiated.')
    return redirect('payments:evpay_lab')


@require_tenant('OWNER', 'MANAGER')
@require_POST
def create_test(request):
    _ensure_pilot(request)
    form = EvPayTestForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid test request. Use an amount of at least TZS 100 and a valid TZ phone.')
        return redirect('payments:evpay_lab')
    data = form.cleaned_data
    try:
        phone = normalize_msisdn(data['phone'])
        if settings.EVPAY_ENVIRONMENT == 'live':
            # Short-lived, server-side protection from double-clicking a REAL debit.
            # Production must use a shared Redis cache across all Django workers.
            key = 'evpay-live-click-' + hashlib.sha256(
                f'{request.active_company.pk}:{request.user.pk}:{phone}'.encode('ascii')).hexdigest()
            if not cache.add(key, 1, timeout=45):
                messages.error(request, 'A live request was just submitted to this phone. Check its status before trying again.')
                return redirect('payments:evpay_lab')
        test = new_test(company=request.active_company, user=request.user, operator=data['operator'],
                        phone=phone, amount=data['amount'])
        try:
            reply = initiate_ussd(test)
        except EvPayError as exc:
            EvPayTestPayment.objects.filter(pk=test.pk, status='CREATED').update(status='UNKNOWN', last_error=str(exc)[:250])
            messages.error(request, 'Request not confirmed: ' + str(exc) + ' Reconcile this reference before trying again.')
        else:
            # Webhook might arrive before POST completes. Never overwrite a verified outcome.
            EvPayTestPayment.objects.filter(pk=test.pk, status='CREATED').update(
                status='PENDING', transaction_id=str(reply.get('transactionId') or '')[:100], last_error='')
            messages.success(request, 'EvPay accepted the request. Awaiting signed confirmation or reconciliation.')
    except (EvPayError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect('payments:evpay_lab')


@require_tenant('OWNER', 'MANAGER')
@require_POST
def reconcile_test(request, pk):
    _ensure_pilot(request)
    obj = get_object_or_404(EvPayTestPayment, company=request.active_company, pk=pk)
    if obj.environment != settings.EVPAY_ENVIRONMENT:
        messages.error(request, 'Cannot reconcile a payment from a different environment.')
        return redirect('payments:evpay_lab')
    try:
        data = retrieve_ussd(obj.reference)
        # Unified status reference may be customReference, reference, or requestId.
        returned_ref = data.get('customReference') or data.get('reference') or data.get('requestId')
        if returned_ref != obj.reference:
            raise EvPayError('Provider returned a different payment reference; no status was applied.')
        apply_status(reference=obj.reference, status=data.get('status'), amount=data.get('amount'),
                     currency=data.get('currency'), transaction_id=data.get('transRef') or data.get('transactionId') or '',
                     fsp_reference=data.get('mnoRef') or data.get('fspReference') or '', source='POLL')
    except (EvPayError, ValueError, LookupError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'Payment reconciled against authenticated EvPay API. No internet access was activated.')
    return redirect('payments:evpay_lab')


@csrf_exempt  # Machine-to-machine only: enforce EvPay HMAC-SHA256 on raw request bytes.
@require_POST
def webhook(request, token):
    expected = getattr(settings, 'EVPAY_WEBHOOK_TOKEN', '')
    secret = getattr(settings, 'EVPAY_WEBHOOK_SECRET', '')
    if not expected or not secret or not settings.EVPAY_ENABLED or not secrets.compare_digest(token, expected):
        return JsonResponse({'error': 'Forbidden'}, status=401)
    raw = request.body
    if len(raw) > 200000 or not verify_webhook(raw, request.headers.get('X-EvPay-Signature', ''), secret):
        return JsonResponse({'error': 'Invalid signature'}, status=401)
    delivery_id = request.headers.get('X-EvPay-Delivery', '')
    event_header = request.headers.get('X-EvPay-Event', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', delivery_id):
        return HttpResponseBadRequest('Missing delivery reference')
    try:
        payload = json.loads(raw)
        event = payload['event']
        data = payload['data']
        if not isinstance(data, dict) or event not in EVENT_STATUSES or event != event_header:
            raise ValueError('Unexpected payment event')
        if payload.get('timestamp') != int(dict(piece.strip().split('=', 1) for piece in request.headers['X-EvPay-Signature'].split(',')).get('t')):
            raise ValueError('Timestamp disagreement')
        status = str(data.get('status', '')).upper()
        if status != EVENT_STATUSES[event]:
            raise ValueError('Event and status disagree')
        apply_status(reference=data.get('orderReference'), status=status, amount=data.get('amount'),
                     currency=data.get('currency'), transaction_id=data.get('id') or '',
                     fsp_reference=data.get('fspReference') or '', delivery_id=delivery_id, event=event)
    except (ValueError, TypeError, KeyError, LookupError, IntegrityError):
        return JsonResponse({'error': 'Unmatched or invalid payment event'}, status=400)
    response = JsonResponse({'status': 'OK'})
    response['Cache-Control'] = 'no-store'
    return response
