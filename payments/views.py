from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.http import HttpResponseNotAllowed, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone
from tenants.utils import require_tenant
from .models import PaymentOrder
from .services import update_order_status


@require_tenant()
def orders(request):
    qs = PaymentOrder.objects.filter(company=request.active_company).select_related('plan', 'method', 'verified_by')
    status = request.GET.get('status', '').upper()
    if status in PaymentOrder.Status.values:
        qs = qs.filter(status=status)
    query = request.GET.get('q', '').strip()[:80]
    if query:
        qs = qs.filter(Q(reference__icontains=query) | Q(customer_name__icontains=query) | Q(customer_phone__icontains=query))
    counts = PaymentOrder.objects.filter(company=request.active_company).aggregate(
        total=Count('id'), pending=Count('id', filter=Q(status='PENDING')),
        paid=Count('id', filter=Q(status='PAID')), revenue=Sum('amount', filter=Q(status='PAID')),
    )
    return render(request, 'payments/orders.html', {'orders': qs[:150], 'counts': counts, 'status_filter': status, 'q': query, 'page_title': 'Payment requests'})


@require_tenant()
def order_detail(request, pk):
    order = get_object_or_404(PaymentOrder.objects.select_related('method', 'plan', 'verified_by'), pk=pk, company=request.active_company)
    return render(request, 'payments/order_detail.html', {'order': order, 'audits': order.audit_entries.select_related('actor'), 'page_title': 'Payment request details'})


@require_tenant('OWNER', 'MANAGER')
@require_POST
def verify_order(request, pk):
    order = get_object_or_404(PaymentOrder, pk=pk, company=request.active_company)
    reference = request.POST.get('merchant_reference', '').strip()[:100]
    note = request.POST.get('review_note', '').strip()[:250]
    if len(reference) < 3:
        messages.error(request, 'Enter the transaction/receipt reference you verified against your merchant statement.')
    elif update_order_status(order=order, actor=request.user, status=PaymentOrder.Status.PAID, merchant_reference=reference, note=note):
        messages.success(request, 'Payment manually verified. Wi-Fi access was NOT activated.')
    else:
        messages.error(request, 'This request has already been processed.')
    return redirect('payments:order_detail', pk=pk)


@require_tenant('OWNER', 'MANAGER')
@require_POST
def cancel_order(request, pk):
    order = get_object_or_404(PaymentOrder, pk=pk, company=request.active_company)
    if update_order_status(order=order, actor=request.user, status=PaymentOrder.Status.CANCELLED, note='Cancelled by authorized business staff.'):
        messages.success(request, 'Payment request cancelled.')
    else:
        messages.error(request, 'This request is already processed.')
    return redirect('payments:order_detail', pk=pk)


@require_tenant('OWNER', 'MANAGER')
def methods(request):
    raise Http404('Manual payment setup is retired. Use verified EvPay or sold vouchers.')


@require_tenant('OWNER', 'MANAGER')
def method_create(request):
    raise Http404('Manual payment setup is retired.')


@require_tenant('OWNER', 'MANAGER')
def method_edit(request, pk):
    raise Http404('Manual payment setup is retired.')


@require_tenant('OWNER', 'MANAGER')
@require_POST
def method_disable(request, pk):
    raise Http404('Manual payment setup is retired.')
