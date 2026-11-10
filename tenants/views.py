from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, redirect
from .forms import CompanyForm
from .models import Membership
from .utils import active_membership, require_tenant

@login_required
def no_company(request):
    return render(request, 'tenants/no_company.html', {'page_title': 'Business access'})

@login_required
def switch_company(request):
    memberships = Membership.objects.filter(user=request.user).select_related('company').order_by('company__name')
    if request.method == 'POST':
        membership = memberships.filter(company_id=request.POST.get('company_id')).first()
        if membership:
            request.session['active_company_id'] = membership.company_id
            messages.success(request, 'Business switched successfully.')
            return redirect('cloud:dashboard')
        messages.error(request, 'Business not found in your account.')
    return render(request, 'tenants/switch.html', {'memberships': memberships, 'page_title': 'Switch business'})

@require_tenant('OWNER', 'MANAGER')
def settings(request):
    company = request.active_company
    form = CompanyForm(request.POST or None, request.FILES or None, instance=company)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Business information updated.')
        return redirect('tenants:settings')
    return render(request, 'tenants/settings.html', {'form': form, 'page_title': 'Business settings'})
