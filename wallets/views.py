"""Owner money views and separate WorldLink-only manual settlement queue."""
import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.http import Http404

from tenants.models import Company
from tenants.utils import require_tenant
from controlcenter.auth import platform_required, platform_can_manage
from .forms import CollectionForm, DestinationForm, DestinationReviewForm, WithdrawalForm, WithdrawalReviewForm, localize_wallet_form
from .models import BusinessWallet, SettledCollection, WithdrawalDestination, WithdrawalRequest
from .services import (
    cancel_withdrawal, claim_withdrawal, finish_withdrawal, record_settled_collection,
    request_withdrawal, review_destination,
)
from django.db.models import Sum
from payments.models import EvPayCollection
from payments.collections import EARNING_STATUSES


def _balance(company):
    return BusinessWallet.objects.filter(company=company).first()


@require_tenant('OWNER')
@never_cache
def dashboard(request):
    company = request.active_company
    wallet = _balance(company)
    destinations = WithdrawalDestination.objects.filter(company=company)
    withdrawals = WithdrawalRequest.objects.filter(company=company).select_related('destination', 'requested_by')[:30]
    collections = SettledCollection.objects.filter(wallet__company=company)[:15]
    evpay = EvPayCollection.objects.filter(company=company, status__in=EARNING_STATUSES)
    uncredited = evpay.exclude(reference__in=SettledCollection.objects.filter(
        wallet__company=company).values('source_reference'))
    return render(request, 'wallets/dashboard.html', {
        'page_title': 'Money & withdrawals', 'wallet': wallet,
        'destinations': destinations, 'withdrawals': withdrawals, 'collections': collections,
        'can_withdraw': request.active_membership.role == 'OWNER',
        'evpay_verified_total': evpay.aggregate(total=Sum('amount'))['total'] or 0,
        'evpay_provider_settled': evpay.filter(status=EvPayCollection.Status.SETTLED).aggregate(total=Sum('amount'))['total'] or 0,
        'evpay_waiting_clearance': uncredited.aggregate(total=Sum('amount'))['total'] or 0,
        'recent_evpay': evpay.select_related('plan')[:15],
    })


@require_tenant('OWNER')
@never_cache
def destination_add(request):
    form = localize_wallet_form(DestinationForm(request.POST or None, user=request.user), request)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.company = request.active_company
        obj.created_by = request.user
        if WithdrawalDestination.objects.filter(company=obj.company, provider=obj.provider,
                                                phone=obj.phone, status__in=['PENDING', 'VERIFIED']).exists():
            form.add_error('phone', 'This number has already been submitted. WorldLink must review the existing record.')
        else:
            try:
                obj.save()
            except IntegrityError:
                form.add_error('phone', 'This number has already been submitted.')
            else:
                messages.success(request, 'Number sent to WorldLink for verification. Withdrawals are locked until approval.')
                return redirect('wallets:dashboard')
    return render(request, 'wallets/form.html', {
        'page_title': 'Add receiving number', 'form': form, 'form_title': 'Verify a receiving number',
        'explanation': 'Enter the real mobile-money number and name. WorldLink will independently verify ownership before any withdrawal.',
        'submit_label': 'Send for verification',
    })


@require_tenant('OWNER')
@never_cache
def withdrawal_new(request):
    form = localize_wallet_form(WithdrawalForm(request.POST or None, company=request.active_company, user=request.user), request)
    if request.method == 'POST' and form.is_valid():
        key = request.POST.get('request_key', '')
        if key != request.session.get('wallet_request_nonce') or not key:
            form.add_error(None, 'This form has expired. Reload before submitting another withdrawal.')
        else:
            try:
                request_withdrawal(company=request.active_company, destination=form.cleaned_data['destination'],
                    actor=request.user, amount=form.cleaned_data['amount'], request_key=uuid.UUID(key))
            except (ValueError, IntegrityError) as exc:
                form.add_error(None, str(exc) if isinstance(exc, ValueError) else 'This withdrawal was already submitted.')
            else:
                request.session.pop('wallet_request_nonce', None)
                messages.success(request, 'Withdrawal requested. WorldLink will review and send money manually.')
                return redirect('wallets:dashboard')
    if not request.session.get('wallet_request_nonce'):
        request.session['wallet_request_nonce'] = str(uuid.uuid4())
    return render(request, 'wallets/form.html', {
        'page_title': 'Request withdrawal', 'form': form, 'form_title': 'Request a withdrawal',
        'explanation': 'Your requested amount is reserved immediately. WorldLink will send it to your verified number after manual review. No money is sent by this form.',
        'submit_label': 'Submit withdrawal request', 'request_key': request.session['wallet_request_nonce'],
    })


@require_tenant('OWNER')
@require_POST
def withdrawal_cancel(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk, company=request.active_company)
    try:
        cancel_withdrawal(withdrawal=withdrawal, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'Withdrawal cancelled and reserved balance released.')
    return redirect('wallets:dashboard')


@platform_required()
@never_cache
def queue(request):
    pending = WithdrawalRequest.objects.filter(status__in=['REQUESTED', 'PROCESSING']).select_related('company', 'destination', 'requested_by')
    numbers = WithdrawalDestination.objects.filter(status='PENDING').select_related('company', 'created_by')
    recent = WithdrawalRequest.objects.exclude(status__in=['REQUESTED', 'PROCESSING']).select_related('company')[:20]
    waiting_evpay = EvPayCollection.objects.filter(status__in=EARNING_STATUSES).exclude(
        reference__in=SettledCollection.objects.values('source_reference')).select_related('company', 'plan')[:30]
    return render(request, 'wallets/queue.html', {
        'page_title': 'Withdrawals · WorldLink', 'pending': pending, 'numbers': numbers,
        'recent': recent, 'can_manage_finance': platform_can_manage(request.user),
        'wallet_total': sum((w.available for w in BusinessWallet.objects.all()), 0),
        'reserved_total': sum((w.reserved for w in BusinessWallet.objects.all()), 0),
        'waiting_evpay': waiting_evpay,
    })


@platform_required(manage=True)
@require_POST
def destination_review(request, pk):
    obj = get_object_or_404(WithdrawalDestination, pk=pk)
    form = DestinationReviewForm(request.POST)
    action = request.POST.get('action')
    if action not in ('approve', 'reject') or not form.is_valid():
        messages.error(request, 'Choose approve/reject and record independent verification evidence.')
    else:
        try:
            review_destination(destination=obj, actor=request.user, approve=action == 'approve',
                               evidence=form.cleaned_data['evidence'])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, 'Receiving number reviewed.')
    return redirect('wallets:queue')


@platform_required(manage=True)
@never_cache
def withdrawal_detail(request, pk):
    item = get_object_or_404(WithdrawalRequest.objects.select_related('company', 'destination', 'requested_by', 'processed_by'), pk=pk)
    return render(request, 'wallets/detail.html', {'page_title': 'Withdrawal review',
        'item': item, 'form': WithdrawalReviewForm()})


@platform_required(manage=True)
@require_POST
def withdrawal_claim(request, pk):
    item = get_object_or_404(WithdrawalRequest, pk=pk)
    try:
        claim_withdrawal(withdrawal=item, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'Request locked for WorldLink manual payment. Owner cannot cancel while processing.')
    return redirect('wallets:withdrawal_detail', pk=pk)


@platform_required(manage=True)
@require_POST
def withdrawal_review(request, pk):
    item = get_object_or_404(WithdrawalRequest, pk=pk)
    form = WithdrawalReviewForm(request.POST)
    action = request.POST.get('action')
    if action not in ('paid', 'reject') or not form.is_valid():
        messages.error(request, 'Choose a valid review action.')
    else:
        try:
            finish_withdrawal(withdrawal=item, actor=request.user, paid=action == 'paid',
                reference=form.cleaned_data['payout_reference'], note=form.cleaned_data['processing_note'])
        except (ValueError, IntegrityError) as exc:
            messages.error(request, str(exc) if isinstance(exc, ValueError) else 'Transfer ID already used.')
        else:
            messages.success(request, 'Withdrawal marked paid after manual transfer.' if action == 'paid'
                else 'Request rejected; reserved funds were returned to available balance.')
    return redirect('wallets:withdrawal_detail', pk=pk)


@platform_required(manage=True)
@never_cache
def collection_new(request):
    initial = {}
    company_id = request.GET.get('company')
    if company_id and company_id.isdigit() and Company.objects.filter(pk=company_id).exists():
        initial['company_id'] = int(company_id)
    form = localize_wallet_form(CollectionForm(request.POST or None, initial=initial), request)
    company = Company.objects.filter(pk=initial.get('company_id')).first() if initial else None
    if request.method == 'POST' and form.is_valid():
        company = get_object_or_404(Company, pk=form.cleaned_data['company_id'])
        try:
            record_settled_collection(company=company, actor=request.user,
                amount=form.cleaned_data['amount'], source_reference=form.cleaned_data['source_reference'],
                settlement_reference=form.cleaned_data['settlement_reference'])
        except (ValueError, IntegrityError) as exc:
            form.add_error(None, str(exc) if isinstance(exc, ValueError) else 'This payment reference already exists.')
        else:
            messages.success(request, 'Cleared production payment recorded in the owner wallet.')
            return redirect('wallets:queue')
    return render(request, 'wallets/collection.html', {'page_title': 'Record cleared collection',
        'form': form, 'company': company, 'companies': Company.objects.order_by('name')})


@platform_required(manage=True)
@require_POST
def evpay_clearance(request, pk):
    """Finance moves a *specific* provider-confirmed payment into withdrawable funds.

    Settlement is never inferred from an EvPay payment success notification.
    Staff must first check the independent WorldLink merchant/bank statement.
    """
    evidence = request.POST.get('settlement_reference', '').strip()
    if len(evidence) < 6 or len(evidence) > 100:
        messages.error(request, 'Enter the actual cleared WorldLink statement reference (6–100 characters).')
        return redirect('wallets:queue')
    try:
        with transaction.atomic():
            payment = get_object_or_404(EvPayCollection.objects.select_for_update(), pk=pk)
            if payment.status not in EARNING_STATUSES:
                raise ValueError('EvPay has not confirmed this transaction or it was reversed.')
            record_settled_collection(company=payment.company, actor=request.user,
                amount=payment.amount, source_reference=payment.reference,
                settlement_reference=evidence)
    except (ValueError, IntegrityError) as exc:
        messages.error(request, str(exc) if isinstance(exc, ValueError)
                       else 'This payment has already been cleared.')
    else:
        messages.success(request, 'Cleared EvPay collection added to the correct business wallet.')
    return redirect('wallets:queue')
