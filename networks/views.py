from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models.deletion import ProtectedError
from django.views.decorators.http import require_POST
from tenants.utils import require_tenant
from .models import Location, Router, WifiPlan
from .forms import LocationForm, RouterForm, WifiPlanForm

@require_tenant()
def router_list(request):
    routers = Router.objects.filter(company=request.active_company).select_related('location')
    return render(request, 'networks/routers.html', {'routers': routers, 'page_title': 'Routers'})

@require_tenant('OWNER','MANAGER','TECHNICIAN')
def router_edit(request, pk=None):
    obj = get_object_or_404(Router, pk=pk, company=request.active_company) if pk else None
    form = RouterForm(request.POST or None, instance=obj, company=request.active_company)
    if request.method == 'POST' and form.is_valid():
        router = form.save(commit=False)
        router.company = request.active_company
        router.save()
        messages.success(request, 'Router inventory saved. Live integration is not connected yet.')
        return redirect('networks:routers')
    return render(request,'networks/form.html',{'form':form,'page_title':'Edit router' if obj else 'Add router','form_type':'router'})

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
