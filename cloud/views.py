from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model,login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render,redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from .forms import EmailLoginForm, SignupForm, ExpenseForm
from .models import Expense
from tenants.models import Company,Membership
from tenants.utils import require_tenant,active_membership
from networks.models import Router, WifiPlan,Location
from vouchers.models import Voucher,ManualSale,VoucherBatch
from hotspots.models import HotspotCustomer, HotspotSession

class LoginPage(LoginView):
    form_class = EmailLoginForm
    template_name = 'auth/login.html'
    redirect_authenticated_user = True

    def get_portal(self):
        source = self.request.POST if self.request.method == 'POST' else self.request.GET
        return 'staff' if source.get('portal') == 'staff' else 'business'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['portal'] = self.get_portal()
        return context

    def form_valid(self, form):
        from controlcenter.auth import platform_can_view
        user = form.get_user()
        if self.get_portal() == 'staff' and not platform_can_view(user):
            form.add_error(None, 'This account is not authorized for the WorldLink team portal.')
            return self.form_invalid(form)
        if self.get_portal() == 'business' and not Membership.objects.filter(user=user).exists():
            form.add_error(None, 'This account has no business workspace. WorldLink team members should choose Staff login.')
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        from controlcenter.auth import platform_can_view
        user = self.request.user
        if (self.get_portal() == 'staff' and platform_can_view(user)) or (platform_can_view(user) and not Membership.objects.filter(user=user).exists()):
            return reverse_lazy('controlcenter:overview')
        # Do not use arbitrary next URLs across different account areas.
        return reverse_lazy('cloud:dashboard')

class SignupPage(View):
    def dispatch(self,request,*args,**kwargs):
        if not settings.ALLOW_PUBLIC_SIGNUP:
            return render(request,'auth/registration_closed.html',status=403)
        return super().dispatch(request,*args,**kwargs)
    def get(self,request):
        if request.user.is_authenticated:
            return redirect('cloud:dashboard')
        return render(request,'auth/register.html',{'form':SignupForm()})
    def post(self,request):
        if request.user.is_authenticated:
            return redirect('cloud:dashboard')
        form=SignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user=get_user_model().objects.create_user(username=form.cleaned_data['email'],email=form.cleaned_data['email'],password=form.cleaned_data['password1'],first_name=form.cleaned_data['name'])
                company=Company.objects.create(name=form.cleaned_data['business'],email=user.email)
                Membership.objects.create(user=user,company=company,role=Membership.Role.OWNER)
            login(request,user)
            request.session['active_company_id']=company.pk
            messages.success(request,'Your WorldLink business workspace is ready.')
            return redirect('cloud:dashboard')
        return render(request,'auth/register.html',{'form':form})

def home(request):
    if request.user.is_authenticated:
        return redirect('cloud:dashboard')
    return render(request,'cloud/landing.html')

@require_tenant()
def dashboard(request):
    company=request.active_company
    data={
        'page_title':'Dashboard',
        'router_count':Router.objects.filter(company=company).count(),
        'location_count':Location.objects.filter(company=company).count(),
        'plan_count':WifiPlan.objects.filter(company=company,is_active=True).count(),
        'vouchers_count':Voucher.objects.filter(company=company).count(),
        'ready_count':Voucher.objects.filter(company=company,status=Voucher.Status.READY).count(),
        'sold_count':Voucher.objects.filter(company=company,status=Voucher.Status.SOLD).count(),
        'total_sales':ManualSale.objects.filter(company=company).aggregate(total=Sum('amount'))['total'] or 0,
        'total_expenses':Expense.objects.filter(company=company).aggregate(total=Sum('amount'))['total'] or 0,
        'recent_sales':ManualSale.objects.filter(company=company).select_related('voucher__batch__plan','recorded_by')[:6],
        'recent_routers':Router.objects.filter(company=company).select_related('location')[:5],
        'hotspot_customer_count':HotspotCustomer.objects.filter(company=company).count(),
        'online_session_count':HotspotSession.objects.filter(company=company).filter(HotspotSession.online_filter()).count(),
        'recent_sessions':HotspotSession.objects.filter(company=company).select_related('router','plan','customer')[:5],
    }
    return render(request,'cloud/dashboard.html',data)

@require_tenant()
def reports(request):
    company=request.active_company
    today=timezone.localdate()
    days=[]
    sales=ManualSale.objects.filter(company=company,created_at__date__gte=today-timedelta(days=6)).values('created_at__date').annotate(total=Sum('amount'))
    lookup={str(x['created_at__date']):float(x['total']) for x in sales}
    for back in range(6,-1,-1):
        date=today-timedelta(days=back)
        days.append({'label':date.strftime('%a %d'),'amount':lookup.get(str(date),0)})
    maximum=max([d['amount'] for d in days] or [0])
    for item in days:
        item['height']=round((item['amount']/maximum)*100) if maximum else 0
    recent=ManualSale.objects.filter(company=company).select_related('voucher__batch__plan','recorded_by')[:60]
    return render(request,'cloud/reports.html',{'page_title':'Sales reports','days':days,'recent':recent,'total':ManualSale.objects.filter(company=company).aggregate(total=Sum('amount'))['total'] or 0, 'expenses_total':Expense.objects.filter(company=company).aggregate(total=Sum('amount'))['total'] or 0})

@login_required
def profile(request):
    return render(request,'cloud/profile.html',{'page_title':'My profile'})

def language_change(request):
    if request.method!='POST':
        return redirect('cloud:home')
    selected=request.POST.get('language','en')
    request.session['ui_lang']=selected if selected in ('en','sw') else 'en'
    target=request.POST.get('next','/')
    if not url_has_allowed_host_and_scheme(target,allowed_hosts={request.get_host()},require_https=request.is_secure()):
        target='/'
    return redirect(target)


@require_tenant()
def expenses(request):
    qs = Expense.objects.filter(company=request.active_company)
    total = qs.aggregate(total=Sum('amount'))['total'] or 0
    return render(request, 'cloud/expenses.html', {'page_title':'Expenses','expenses':qs[:150], 'expenses_total':total})

@require_tenant('OWNER', 'MANAGER')
def expense_edit(request, pk=None):
    obj = get_object_or_404(Expense, pk=pk, company=request.active_company) if pk else None
    form = ExpenseForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        expense = form.save(commit=False)
        expense.company = request.active_company
        if not expense.pk:
            expense.recorded_by = request.user
        expense.save()
        messages.success(request, 'Expense saved.')
        return redirect('cloud:expenses')
    if request.method == 'GET' and not obj:
        form.fields['date'].initial = timezone.localdate()
    return render(request, 'cloud/expense_form.html', {'form':form, 'page_title':'Edit expense' if obj else 'Add expense'})

@require_tenant('OWNER', 'MANAGER')
@require_POST
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, company=request.active_company)
    expense.delete()
    messages.success(request, 'Expense deleted.')
    return redirect('cloud:expenses')
