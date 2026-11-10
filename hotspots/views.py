"""Tenant-scoped hotspot observations; no fake live connect/disconnect actions."""
import csv
from datetime import timedelta
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from tenants.utils import require_tenant
from networks.models import Router, WifiPlan
from .forms import CustomerForm
from .models import HotspotCustomer, HotspotSession


def filtered_sessions(request):
    company=request.active_company
    qs=HotspotSession.objects.filter(company=company).select_related('customer','router','plan','voucher')
    q=request.GET.get('q','').strip()[:120]
    if q:
        qs=qs.filter(Q(username__icontains=q)|Q(mac_address__icontains=q)|Q(ip_address__icontains=q)|Q(customer__full_name__icontains=q)|Q(customer__phone__icontains=q))
    router=request.GET.get('router','')
    if router.isdecimal(): qs=qs.filter(router_id=int(router))
    plan=request.GET.get('plan','')
    if plan.isdecimal(): qs=qs.filter(plan_id=int(plan))
    state=request.GET.get('state','all')
    if state=='online': qs=qs.filter(HotspotSession.online_filter())
    elif state=='demo': qs=qs.filter(source='DEMO')
    elif state=='offline': qs=qs.exclude(HotspotSession.online_filter())
    elif state in ('ACTIVE','ENDED','DISCONNECTED','EXPIRED'): qs=qs.filter(status=state)
    return qs


@require_tenant()
def sessions(request):
    company=request.active_company
    base=HotspotSession.objects.filter(company=company)
    now=timezone.now()
    byte_totals=base.aggregate(dl=Sum('bytes_download'),ul=Sum('bytes_upload'))
    stats={
        'online_count':base.filter(HotspotSession.online_filter(now)).count(),
        'session_count':base.count(),
        'demo_count':base.filter(source='DEMO').count(),
        'stale_count':base.filter(status='ACTIVE',source__in=('RADIUS','OMADA'),last_seen_at__lt=now-timedelta(minutes=5)).count(),
        'total_mb':round(((byte_totals['dl'] or 0)+(byte_totals['ul'] or 0))/1048576,1),
    }
    page=Paginator(filtered_sessions(request),25).get_page(request.GET.get('page'))
    return render(request,'hotspots/sessions.html',{'page_title':'Connected users','records':page,'stats':stats,
        'routers':Router.objects.filter(company=company).order_by('name'), 'plans':WifiPlan.objects.filter(company=company).order_by('name'),
        'filter_q':request.GET.get('q',''),'filter_state':request.GET.get('state','all'),
        'filter_router':request.GET.get('router',''),'filter_plan':request.GET.get('plan',''),
        'query_string':request.GET.urlencode(), 'now':now})


@require_tenant()
def session_detail(request,pk):
    record=get_object_or_404(HotspotSession.objects.select_related('customer','router','router__location','plan','voucher'),pk=pk,company=request.active_company)
    return render(request,'hotspots/session_detail.html',{'page_title':'Session details','record':record})


@require_tenant()
def sessions_export(request):
    response=HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition']='attachment; filename="worldlink-sessions.csv"'
    writer=csv.writer(response)
    writer.writerow(['Customer','Username','Device MAC','IP','Router','Package','Source','Status','Online observed','Start','Expiry','Last seen','Download bytes','Upload bytes'])
    # Prefix spreadsheet-formula prefixes in free-text CSV fields.
    def cell(value):
        text = str(value or '')
        return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text
    for s in filtered_sessions(request).iterator(chunk_size=500):
        writer.writerow([cell(s.customer.full_name if s.customer else ''),cell(s.username),cell(s.mac_address),s.ip_address or '',cell(s.router.name),cell(s.plan.name),s.get_source_display(),s.get_status_display(),s.online,s.started_at.isoformat(),s.expires_at.isoformat() if s.expires_at else '',s.last_seen_at.isoformat() if s.last_seen_at else '',s.bytes_download,s.bytes_upload])
    return response


@require_tenant()
def customers(request):
    qs=HotspotCustomer.objects.filter(company=request.active_company)
    q=request.GET.get('q','').strip()[:120]
    if q: qs=qs.filter(Q(full_name__icontains=q)|Q(phone__icontains=q)|Q(email__icontains=q))
    page=Paginator(qs,25).get_page(request.GET.get('page'))
    return render(request,'hotspots/customers.html',{'page_title':'Wi-Fi customers','records':page,'filter_q':q,'customer_count':HotspotCustomer.objects.filter(company=request.active_company).count()})


@require_tenant()
def customer_detail(request,pk):
    customer=get_object_or_404(HotspotCustomer,pk=pk,company=request.active_company)
    records=HotspotSession.objects.filter(company=request.active_company,customer=customer).select_related('router','plan')[:50]
    return render(request,'hotspots/customer_detail.html',{'page_title':'Customer details','customer':customer,'records':records})


@require_tenant('OWNER','MANAGER','CASHIER')
def customer_edit(request,pk=None):
    obj=get_object_or_404(HotspotCustomer,pk=pk,company=request.active_company) if pk else None
    form=CustomerForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        customer=form.save(commit=False)
        customer.company=request.active_company
        customer.save()
        messages.success(request,'Customer saved successfully.')
        return redirect('hotspots:customer_detail',pk=customer.pk)
    return render(request,'hotspots/customer_form.html',{'page_title':'Edit customer' if obj else 'New customer','form':form,'editing':bool(obj)})


@require_tenant('OWNER','MANAGER')
@require_POST
def customer_delete(request,pk):
    customer=get_object_or_404(HotspotCustomer,pk=pk,company=request.active_company)
    if customer.sessions.exists():
        messages.error(request,'Cannot delete a customer with session history. Edit their details instead.')
    else:
        customer.delete()
        messages.success(request,'Customer deleted.')
    return redirect('hotspots:customers')
