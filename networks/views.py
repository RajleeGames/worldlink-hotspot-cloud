from django.contrib import messages
from django.views.decorators.debug import sensitive_post_parameters
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models.deletion import ProtectedError
from django.db.models import Count
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from tenants.utils import require_tenant
from vouchers.models import Voucher
from .models import Location, Router, RouterVoucherSync, WifiPlan
from .forms import LocationForm, MikroTikLoginForm, RouterForm, WifiPlanForm
from .mikrotik import MikroTikClient, RouterConnectionError

@require_tenant()
def router_list(request):
    routers = Router.objects.filter(company=request.active_company).select_related('location').annotate(
        synced_vouchers=Count('voucher_syncs')
    )
    return render(request, 'networks/routers.html', {'routers': routers, 'page_title': 'Routers'})

@require_tenant('OWNER','MANAGER','TECHNICIAN')
def router_edit(request, pk=None):
    obj = get_object_or_404(Router, pk=pk, company=request.active_company) if pk else None
    form = RouterForm(request.POST or None, instance=obj, company=request.active_company)
    if request.method == 'POST' and form.is_valid():
        router = form.save(commit=False)
        router.company = request.active_company
        if router.location_id is None:
            router.location, _ = Location.objects.get_or_create(
                company=request.active_company, name='Main site',
            )
        router.save()
        messages.success(request, 'Router saved. Use Connect & sync to test a MikroTik gateway.')
        return redirect('networks:routers')
    return render(request,'networks/form.html',{'form':form,'page_title':'Edit router' if obj else 'Add router','form_type':'router'})


@require_tenant('OWNER', 'MANAGER', 'TECHNICIAN')
@never_cache
@sensitive_post_parameters('password')
def router_connect(request, pk):
    router = get_object_or_404(Router, pk=pk, company=request.active_company)
    if router.family != Router.Family.MIKROTIK:
        messages.error(request, 'Live connection for this brand is not available. MikroTik RouterOS v7 is supported in this pilot.')
        return redirect('networks:routers')
    form = MikroTikLoginForm(request.POST or None)
    info = None
    sync_count = None
    online_users = None
    online_total = None
    sold = Voucher.objects.filter(
        company=request.active_company, status=Voucher.Status.SOLD, manual_sale__isnull=False
    ).exclude(router_syncs__router=router).count()
    if request.method == 'POST' and form.is_valid():
        action = request.POST.get('action')
        if action not in ('test', 'sync', 'online'):
            form.add_error(None, 'Choose Test connection, View live users or Sync sold vouchers.')
        else:
            try:
                api = MikroTikClient(
                    router, form.cleaned_data['username'], form.cleaned_data['password'],
                    verify_tls=form.cleaned_data['verify_tls'],
                )
                info = api.check_ready()
                router.last_checked_at = timezone.now()
                router.save(update_fields=['last_checked_at'])
                if action == 'sync':
                    sync_count = api.sync_sold_vouchers(router, request.user, max_count=10)
                    sold = Voucher.objects.filter(
                        company=request.active_company, status=Voucher.Status.SOLD, manual_sale__isnull=False
                    ).exclude(router_syncs__router=router).count()
                    messages.success(
                        request,
                        f'{sync_count} paid-manually sold vouchers confirmed on MikroTik. '
                        'Only these router users may log in; no EvPay sandbox orders were activated.'
                    )
                elif action == 'online':
                    online_users, online_total = api.active_users()
                    messages.success(request, 'Read-only snapshot received directly from MikroTik HotSpot Active.')
                else:
                    messages.success(request, 'RouterOS HTTPS connection successful. No router settings were changed.')
            except RouterConnectionError as exc:
                messages.error(request, str(exc))
    elif request.method == 'POST':
        messages.error(request, 'Check the RouterOS username, password and certificate choice.')
    response = render(request, 'networks/router_connect.html', {
        'router': router, 'form': form, 'info': info, 'sync_count': sync_count,
        'unsynced_sold': sold, 'synced_count': RouterVoucherSync.objects.filter(router=router).count(),
        'online_users': online_users, 'online_total': online_total,
        'page_title': 'Connect MikroTik',
    })
    response['Referrer-Policy'] = 'no-referrer'
    response['Cache-Control'] = 'private, no-store'
    return response

@require_tenant()
def location_list(request):
    return render(request, 'networks/locations.html', {'locations':Location.objects.filter(company=request.active_company).order_by('name'),'page_title':'Locations'})

@require_tenant('OWNER','MANAGER','TECHNICIAN')
def location_add(request, pk=None):
    obj = get_object_or_404(Location, pk=pk, company=request.active_company) if pk else None
    form = LocationForm(request.POST or None, instance=obj, company=request.active_company)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.company = request.active_company
        obj.save()
        messages.success(request,'Location saved.')
        return redirect('networks:locations')
    return render(request,'networks/form.html',{'form':form,'page_title':'Edit location' if obj else 'Add location','form_type':'location'})

@require_tenant()
def plan_list(request):
    return render(request,'networks/plans.html',{'plans':WifiPlan.objects.filter(company=request.active_company),'page_title':'Wi-Fi packages'})

@require_tenant('OWNER','MANAGER')
def plan_edit(request,pk=None):
    obj = get_object_or_404(WifiPlan,pk=pk,company=request.active_company) if pk else None
    form = WifiPlanForm(request.POST or None,instance=obj)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.company = request.active_company
        obj.save()
        messages.success(request,'Package saved.')
        return redirect('networks:plans')
    return render(request,'networks/form.html',{'form':form,'page_title':'Edit package' if obj else 'Create package','form_type':'plan'})


@require_tenant('OWNER', 'MANAGER', 'TECHNICIAN')
@require_POST
def router_delete(request, pk):
    router = get_object_or_404(Router, pk=pk, company=request.active_company)
    router.delete()
    messages.success(request, 'Router removed from inventory.')
    return redirect('networks:routers')

@require_tenant('OWNER', 'MANAGER', 'TECHNICIAN')
@require_POST
def location_delete(request, pk):
    location = get_object_or_404(Location, pk=pk, company=request.active_company)
    try:
        location.delete()
        messages.success(request, 'Location removed.')
    except ProtectedError:
        messages.error(request, 'Move or remove routers at this location before deleting it.')
    return redirect('networks:locations')

@require_tenant('OWNER', 'MANAGER')
@require_POST
def plan_delete(request, pk):
    plan = get_object_or_404(WifiPlan, pk=pk, company=request.active_company)
    try:
        plan.delete()
        messages.success(request, 'Package removed.')
    except ProtectedError:
        messages.error(request, 'This package has voucher history. Disable it instead of deleting it.')
    return redirect('networks:plans')
