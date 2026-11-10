import secrets
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.shortcuts import render,redirect,get_object_or_404
from django.utils.html import escape
from tenants.utils import require_tenant
from .models import VoucherBatch,Voucher,ManualSale
from .forms import BatchForm,ManualSaleForm,BatchLabelForm

ALPHABET='23456789ABCDEFGHJKLMNPQRSTUVWXYZ'

def secure_code():
    return 'WHC-' + ''.join(secrets.choice(ALPHABET) for _ in range(10))

@require_tenant()
def batch_list(request):
    batches=VoucherBatch.objects.filter(company=request.active_company).select_related('plan','created_by')
    return render(request,'vouchers/batches.html',{'batches':batches,'page_title':'Voucher batches'})

@require_tenant('OWNER','MANAGER','CASHIER')
def batch_create(request):
    form=BatchForm(request.POST or None,company=request.active_company)
    if request.method=='POST' and form.is_valid():
        # Prevent duplicates within a generated batch and across existing codes.
        codes=set()
        while len(codes)<form.cleaned_data['quantity']:
            codes.add(secure_code())
        with transaction.atomic():
            batch=VoucherBatch.objects.create(company=request.active_company,plan=form.cleaned_data['plan'],label=form.cleaned_data['label'],quantity=len(codes),created_by=request.user)
            Voucher.objects.bulk_create([Voucher(company=request.active_company,batch=batch,code=code) for code in codes])
        messages.success(request,f'{len(codes)} unique vouchers created. They are NOT live router credentials yet.')
        return redirect('vouchers:batch_detail',pk=batch.pk)
    return render(request,'vouchers/create.html',{'form':form,'page_title':'Generate vouchers'})

@require_tenant()
def batch_detail(request,pk):
    batch=get_object_or_404(VoucherBatch.objects.select_related('plan'),pk=pk,company=request.active_company)
    vouchers=batch.vouchers.select_related('manual_sale').all()
    return render(request,'vouchers/detail.html',{'batch':batch,'vouchers':vouchers,'page_title':f'Batch #{batch.pk}'})

@require_tenant('OWNER','MANAGER','CASHIER')
def manual_sell(request,pk):
    voucher=get_object_or_404(Voucher.objects.select_related('batch__plan'),pk=pk,company=request.active_company)
    if request.method!='POST':
        return redirect('vouchers:batch_detail',pk=voucher.batch_id)
    form=ManualSaleForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                voucher=Voucher.objects.select_for_update().get(pk=pk,company=request.active_company)
                if voucher.status!=Voucher.Status.READY:
                    messages.error(request,'This voucher is not available for manual sale.')
                    return redirect('vouchers:batch_detail',pk=voucher.batch_id)
                ManualSale.objects.create(company=request.active_company,voucher=voucher,amount=voucher.batch.plan.price,method=form.cleaned_data['method'],notes=form.cleaned_data['notes'],recorded_by=request.user)
                voucher.status=Voucher.Status.SOLD
                voucher.save(update_fields=['status'])
                messages.success(request,'Manual sale recorded. No automatic payment or network activation occurred.')
        except IntegrityError:
            messages.error(request,'This voucher has already been sold.')
    else:
        messages.error(request,'Could not record sale. Check the payment method.')
    return redirect('vouchers:batch_detail',pk=voucher.batch_id)

@require_tenant()
def batch_export(request,pk):
    batch=get_object_or_404(VoucherBatch.objects.select_related('plan'),pk=pk,company=request.active_company)
    import csv
    response=HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="worldlink-batch-{batch.pk}.csv"'
    response.write('\ufeff')
    writer=csv.writer(response)
    writer.writerow(['Voucher code','Package','Duration minutes','Price TZS','Recorded status','Warning'])
    for voucher in batch.vouchers.all():
        writer.writerow([voucher.code,batch.plan.name,batch.plan.duration_minutes,batch.plan.price,voucher.status,'NOT ROUTER-ACTIVATED'])
    return response


@require_tenant('OWNER','MANAGER')
def batch_edit(request, pk):
    batch = get_object_or_404(VoucherBatch, pk=pk, company=request.active_company)
    form = BatchLabelForm(request.POST or None, instance=batch)
    if request.method=='POST' and form.is_valid():
        form.save()
        messages.success(request,'Voucher batch label updated.')
        return redirect('vouchers:batch_detail',pk=batch.pk)
    return render(request,'vouchers/edit.html',{'page_title':'Edit batch','batch':batch,'form':form})

@require_tenant('OWNER','MANAGER')
@require_POST
def batch_delete(request, pk):
    with transaction.atomic():
        batch=get_object_or_404(VoucherBatch.objects.select_for_update(),pk=pk,company=request.active_company)
        if batch.vouchers.exclude(status=Voucher.Status.READY).exists():
            messages.error(request,'This batch has sold or voided codes and cannot be deleted.')
            return redirect('vouchers:batch_detail',pk=batch.pk)
        try:
            batch.delete()
            messages.success(request,'Unused batch deleted.')
        except IntegrityError:
            messages.error(request,'This batch has transaction history and cannot be deleted.')
    return redirect('vouchers:batches')
