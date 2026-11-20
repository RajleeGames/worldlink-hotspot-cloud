import hashlib
import uuid

from django.contrib import messages
from django.conf import settings as django_settings
from django.core.cache import cache
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.http import Http404
from django.utils import timezone
from tenants.models import Company
from tenants.utils import require_tenant
from networks.models import WifiPlan
from payments.models import PaymentMethod, PaymentOrder, EvPayCollection
from payments.forms import PublicOrderForm, PublicEvPayForm
from payments.services import create_pending_order
from payments.collections import collection_enabled_for
from payments.evpay import EvPayError, initiate_collection
from payments.collections import start_collection
from payments.omada import controller_context, recent_controller_context
from vouchers.models import VoucherRedemption
from vouchers.services import VoucherError, approved_voucher_route, redeem_voucher
from .models import CaptivePortal
from .forms import CaptivePortalForm
from .words import words_for


def _locale(request):
    return 'sw' if request.GET.get('lang') == 'sw' or request.POST.get('lang') == 'sw' else 'en'


def _business(slug):
    company = get_object_or_404(Company, slug=slug)
    portal = CaptivePortal.objects.filter(company=company, enabled=True).first()
    if company.status == Company.Status.SUSPENDED or portal is None:
        raise Http404('This Wi-Fi portal is not available.')
    return company, portal


def _context(company, portal, lang):
    return {'company': company, 'portal': portal, 'lang': lang, 'w': words_for(lang), 'public_portal': True}


@require_tenant('OWNER', 'MANAGER')
def settings(request):
    portal, _ = CaptivePortal.objects.get_or_create(company=request.active_company)
    form = CaptivePortalForm(request.POST or None, instance=portal)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Guest Wi-Fi portal settings updated. This does not enable network access.')
        return redirect('portal:settings')
    return render(request, 'portal/settings.html', {
        'form': form, 'portal': portal,
        'public_url': request.build_absolute_uri(reverse('portal:public', kwargs={'slug': request.active_company.slug})),
        'page_title': 'Captive portal',
    })


@require_http_methods(['GET'])
def public(request, slug):
    company, portal = _business(slug)
    controller_context(request, company)
    lang = _locale(request)
    plans = WifiPlan.objects.filter(company=company, is_active=True).order_by('price', 'id')
    methods = PaymentMethod.objects.filter(company=company, is_active=True).count()
    omada = recent_controller_context(request, company)
    response = render(request, 'portal/public.html', {
        **_context(company, portal, lang), 'plans': plans, 'methods_count': methods,
        'evpay_available': collection_enabled_for(company)
        and bool(omada),
        'voucher_available': bool(omada and approved_voucher_route(
            company, omada.get('apMac'), omada.get('ssidName'))),
    })
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'same-origin'
    return response


@require_http_methods(['POST'])
def voucher_redeem(request, slug):
    company, portal = _business(slug)
    context = recent_controller_context(request, company)
    # Limit guesses by the *captive client MAC*, not the shared mobile-network
    # egress IP. A real deployment uses WHC_REDIS_URL as the Django cache.
    key_id = (context or {}).get('clientMac', request.META.get('REMOTE_ADDR', 'unknown'))
    bucket = int(timezone.now().timestamp() // 60)
    cache_key = 'whc-voucher-attempt-' + hashlib.sha256(
        f'{company.pk}:{key_id}:{bucket}'.encode('utf-8')).hexdigest()
    attempts = cache.get(cache_key)
    if attempts is None:
        cache.add(cache_key, 0, timeout=75)
    attempts = cache.incr(cache_key)
    try:
        if attempts > 6:
            raise VoucherError('Too many attempts. Wait one minute and try again.')
        if not django_settings.WHC_REDIS_URL and not django_settings.DEBUG:
            raise VoucherError('Voucher activation is temporarily unavailable. Contact the business.')
        redemption = redeem_voucher(company=company,
            raw_code=request.POST.get('code', ''), context=context)
    except VoucherError as exc:
        response = render(request, 'portal/voucher_result.html', {
            **_context(company, portal, _locale(request)), 'error': str(exc),
        }, status=400)
    else:
        return redirect('portal:voucher_status', slug=slug, public_id=redemption.public_id)
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'same-origin'
    return response


@require_http_methods(['GET'])
def voucher_status(request, slug, public_id):
    company, portal = _business(slug)
    redemption = get_object_or_404(
        VoucherRedemption.objects.select_related('voucher__batch__plan'),
        company=company, public_id=public_id,
    )
    context = recent_controller_context(request, company)
    if not context or context.get('clientMac') != redemption.client_mac:
        raise Http404('Reopen this page from your Wi-Fi login session.')
    response = render(request, 'portal/voucher_result.html', {
        **_context(company, portal, _locale(request)), 'redemption': redemption,
    })
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


@require_http_methods(['GET', 'POST'])
def checkout(request, slug, plan_id):
    company, portal = _business(slug)
    lang = _locale(request)
    plan = get_object_or_404(WifiPlan, company=company, id=plan_id, is_active=True)
    methods = PaymentMethod.objects.filter(company=company, is_active=True).order_by('channel', 'id')
    form = PublicOrderForm(request.POST or None, company=company)
    if request.method == 'POST' and form.is_valid():
        # Session throttling is a basic anti-accidental-repeat measure, not a production rate limit.
        # Redis-backed IP/phone throttling and abuse monitoring are required before public launch.
        recent = request.session.get('whc_last_checkout_at', 0)
        if timezone.now().timestamp() - recent < 8:
            form.add_error(None, 'Please wait a moment before making another request.')
        else:
            order = create_pending_order(
                company=company, plan=plan, method=form.cleaned_data['method'],
                name=form.cleaned_data['customer_name'], phone=form.cleaned_data['customer_phone'],
            )
            request.session['whc_last_checkout_at'] = timezone.now().timestamp()
            url = reverse('portal:status', kwargs={'slug': slug, 'public_id': order.public_id})
            return redirect(f'{url}?lang={lang}')
    return render(request, 'portal/checkout.html', {
        **_context(company, portal, lang), 'plan': plan, 'methods': methods, 'form': form,
    })


@require_http_methods(['GET'])
def order_status(request, slug, public_id):
    company, portal = _business(slug)
    order = get_object_or_404(PaymentOrder.objects.select_related('method', 'plan'), company=company, public_id=public_id)
    response = render(request, 'portal/status.html', {**_context(company, portal, _locale(request)), 'order': order})
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


@require_http_methods(['GET', 'POST'])
def evpay_checkout(request, slug, plan_id):
    company, portal = _business(slug)
    if not collection_enabled_for(company):
        raise Http404('Live mobile-money collection is not yet available.')
    plan = get_object_or_404(WifiPlan, company=company, pk=plan_id, is_active=True)
    if plan.price < 100 or plan.price > django_settings.EVPAY_PUBLIC_MAX_AMOUNT_TZS:
        raise Http404('Package is not approved for this pilot.')
    nonce = request.session.setdefault('whc_evpay_checkout_nonce', str(uuid.uuid4()))
    form = PublicEvPayForm(request.POST or None, initial={'nonce': nonce})
    if request.method == 'POST' and form.is_valid():
        if str(form.cleaned_data['nonce']) != nonce:
            form.add_error(None, 'Checkout expired. Reload before trying again.')
        else:
            data = form.cleaned_data
            # Short guard only. Live deployment must use a shared Redis cache.
            key = 'whc-public-push-' + hashlib.sha256(
                f"{company.pk}:{data['phone']}".encode('ascii')).hexdigest()
            if not cache.add(key, 1, timeout=60):
                form.add_error(None, 'A USSD push was sent recently to this phone. Check it before trying again.')
            else:
                try:
                    collection, created = start_collection(company=company, plan=plan,
                        name=data['customer_name'], phone=data['phone'],
                        operator=data['operator'], nonce=data['nonce'],
                        omada_context=recent_controller_context(request, company))
                except ValueError as exc:
                    cache.delete(key)
                    form.add_error(None, str(exc))
                else:
                    request.session.pop('whc_evpay_checkout_nonce', None)
                    if created:
                        try:
                            reply = initiate_collection(collection)
                        except EvPayError:
                            # Never auto-retry an uncertain real debit.
                            EvPayCollection.objects.filter(pk=collection.pk, status='CREATED').update(
                                status='UNKNOWN', last_error='Provider response unconfirmed; reconcile the original reference.')
                        else:
                            EvPayCollection.objects.filter(pk=collection.pk, status='CREATED').update(
                                status='PENDING', transaction_id=str(reply.get('transactionId') or '')[:100])
                    url = reverse('portal:evpay_status', kwargs={'slug': slug, 'public_id': collection.public_id})
                    return redirect(f'{url}?lang={_locale(request)}')
    return render(request, 'portal/evpay_checkout.html', {
        **_context(company, portal, _locale(request)), 'plan': plan, 'form': form,
    })


@require_http_methods(['GET'])
def evpay_status(request, slug, public_id):
    company, portal = _business(slug)
    collection = get_object_or_404(EvPayCollection.objects.select_related('plan'),
                                   company=company, public_id=public_id)
    response = render(request, 'portal/evpay_status.html', {
        **_context(company, portal, _locale(request)), 'collection': collection,
    })
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response
