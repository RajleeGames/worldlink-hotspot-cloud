"""Authenticated EvPay customer callbacks and tenant-scoped review views."""
import hmac
import json
import logging
import re
import secrets
import time

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Sum
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tenants.utils import require_tenant
from .collections import apply_collection_status, EARNING_STATUSES
from .evpay import EvPayError, retrieve_ussd, sign_payload, verify_webhook
from .evpay_lab import EVENT_STATUSES
from .models import EvPayCollection

logger = logging.getLogger(__name__)


def _signature_failure_reason(raw, header):
    """Describe a failed signature safely: never log raw data, HMACs or keys."""
    if not header:
        return 'signature header missing'
    pieces = dict(part.strip().split('=', 1) for part in header.split(',') if '=' in part)
    timestamp, digest = pieces.get('t', ''), pieces.get('v1', '')
    if not re.fullmatch(r'\d{10,11}', timestamp):
        return 'invalid signature timestamp format'
    if not re.fullmatch(r'[a-fA-F0-9]{64}', digest):
        return 'invalid signature HMAC format'
    if abs(int(time.time()) - int(timestamp)) > 300:
        return 'signature timestamp outside five-minute window'
    key = settings.EVPAY_SIG_KEY
    if key and hmac.compare_digest(sign_payload(key, timestamp, raw), digest.lower()):
        return 'HMAC matches API request-signing key, not webhook secret'
    return 'HMAC mismatch; confirm merchant webhook signing secret with EvPay'


@csrf_exempt
@require_POST
def webhook(request, token):
    """Acknowledge only signed, matching provider events; never trust browser posts."""
    expected = settings.EVPAY_COLLECTION_WEBHOOK_TOKEN
    secret = settings.EVPAY_WEBHOOK_SECRET
    if (not expected or not secret or not settings.EVPAY_ENABLED or
            not secrets.compare_digest(token, expected)):
        logger.warning('EvPay collection webhook rejected: route token or configuration mismatch.')
        return JsonResponse({'error': 'Forbidden'}, status=401)
    raw = request.body
    signature = request.headers.get('X-EvPay-Signature', '')
    if len(raw) > 200000 or not verify_webhook(raw, signature, secret):
        logger.warning('EvPay collection webhook rejected: %s.',
            'oversized callback body' if len(raw) > 200000
            else _signature_failure_reason(raw, signature))
        return JsonResponse({'error': 'Invalid signature'}, status=401)
    delivery_id = request.headers.get('X-EvPay-Delivery', '')
    event_header = request.headers.get('X-EvPay-Event', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', delivery_id):
        return HttpResponseBadRequest('Missing delivery reference')
    try:
        payload = json.loads(raw)
        data = payload['data']
        event = payload['event']
        if not isinstance(data, dict) or event not in EVENT_STATUSES or event != event_header:
            raise ValueError('Unexpected event')
        signed_time = int(dict(piece.strip().split('=', 1) for piece in
                          request.headers['X-EvPay-Signature'].split(',')).get('t'))
        if payload.get('timestamp') != signed_time:
            raise ValueError('Inconsistent timestamp')
        status = str(data.get('status', '')).upper()
        if status != EVENT_STATUSES[event]:
            raise ValueError('Inconsistent event status')
        apply_collection_status(reference=data.get('orderReference'), status=status,
            amount=data.get('amount'), currency=data.get('currency'),
            transaction_id=data.get('id') or '', fsp_reference=data.get('fspReference') or '',
            delivery_id=delivery_id, event=event)
    except (ValueError, TypeError, KeyError, LookupError, IntegrityError):
        return JsonResponse({'error': 'Invalid payment event'}, status=400)
    response = JsonResponse({'status': 'OK'})
    response['Cache-Control'] = 'no-store'
    return response


@require_tenant('OWNER', 'MANAGER')
def business_collections(request):
    qs = EvPayCollection.objects.filter(company=request.active_company).select_related('plan')
    confirmed = qs.filter(status__in=EARNING_STATUSES).aggregate(total=Sum('amount'))['total'] or 0
    return render(request, 'payments/collections.html', {
        'page_title': 'EvPay customer collections', 'collections': qs[:100],
        'confirmed': confirmed,
    })


@require_tenant('OWNER', 'MANAGER')
@require_POST
def reconcile(request, pk):
    collection = get_object_or_404(EvPayCollection,
        pk=pk, company=request.active_company)
    key = f'evpay-reconcile-collection-{collection.pk}'
    if not cache.add(key, 1, timeout=30):
        messages.error(request, 'Please wait before checking this payment again.')
    else:
        try:
            data = retrieve_ussd(collection.reference)
            returned_reference = data.get('customReference') or data.get('reference') or data.get('requestId')
            if returned_reference != collection.reference:
                raise ValueError('EvPay returned a different payment reference.')
            apply_collection_status(reference=collection.reference, status=data.get('status'),
                amount=data.get('amount'), currency=data.get('currency'),
                transaction_id=data.get('transRef') or data.get('transactionId') or '',
                fsp_reference=data.get('mnoRef') or data.get('fspReference') or '')
        except (EvPayError, ValueError, LookupError, IntegrityError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, 'EvPay verified this payment against its API.')
    return redirect('payments:business_collections')
