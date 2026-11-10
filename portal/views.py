from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.http import Http404
from django.utils import timezone
from tenants.models import Company
from tenants.utils import require_tenant
from networks.models import WifiPlan
from payments.models import PaymentMethod, PaymentOrder
from payments.forms import PublicOrderForm
from payments.services import create_pending_order
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
    lang = _locale(request)
    plans = WifiPlan.objects.filter(company=company, is_active=True).order_by('price', 'id')
    methods = PaymentMethod.objects.filter(company=company, is_active=True).count()
    return render(request, 'portal/public.html', {**_context(company, portal, lang), 'plans': plans, 'methods_count': methods})


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
