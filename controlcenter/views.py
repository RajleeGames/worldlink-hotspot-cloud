"""WorldLink-only management. Platform staff never acquire tenant ownership."""
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from tenants.models import Company, Membership
from networks.models import Router, WifiPlan
from vouchers.models import Voucher, ManualSale
from hotspots.models import HotspotSession, HotspotCustomer
from .auth import platform_required, platform_can_manage
from .forms import CompanyStatusForm
from .models import PlatformAudit

User=get_user_model()

@platform_required()
def overview(request):
    recent_businesses=Company.objects.order_by('-created_at')[:7]
    latest_audits=PlatformAudit.objects.select_related('actor','company')[:8]
    online=HotspotSession.objects.filter(HotspotSession.online_filter())
    return render(request,'controlcenter/overview.html',{'page_title':'WorldLink Control Center',
        'businesses_count':Company.objects.count(),
        'active_businesses':Company.objects.filter(status='ACTIVE').count(),
        'trial_businesses':Company.objects.filter(status='TRIAL').count(),
        'suspended_businesses':Company.objects.filter(status='SUSPENDED').count(),
        'accounts_count':User.objects.count(), 'memberships_count':Membership.objects.count(),
        'routers_count':Router.objects.count(), 'plans_count':WifiPlan.objects.count(),
        'vouchers_count':Voucher.objects.count(), 'customer_count':HotspotCustomer.objects.count(),
        'online_count':online.count(), 'session_count':HotspotSession.objects.count(),
        'demo_sessions':HotspotSession.objects.filter(source='DEMO').count(),
        'sales_sum':ManualSale.objects.aggregate(total=Sum('amount'))['total'] or 0,
        'recent_businesses':recent_businesses,'latest_audits':latest_audits,
        'can_manage_platform':platform_can_manage(request.user)})

@platform_required()
def businesses(request):
    q=request.GET.get('q','').strip()[:120]
    status=request.GET.get('status','all')
    qs=Company.objects.annotate(member_count=Count('memberships',distinct=True),router_count=Count('routers',distinct=True)).order_by('-created_at')
    if q: qs=qs.filter(Q(name__icontains=q)|Q(email__icontains=q)|Q(slug__icontains=q)|Q(city__icontains=q))
    if status in ('ACTIVE','TRIAL','SUSPENDED'): qs=qs.filter(status=status)
    return render(request,'controlcenter/businesses.html',{'page_title':'All businesses',
        'records':Paginator(qs,25).get_page(request.GET.get('page')),'filter_q':q,'filter_status':status,
        'can_manage_platform':platform_can_manage(request.user)})

@platform_required()
def business_detail(request,pk):
    company=get_object_or_404(Company,pk=pk)
    form=CompanyStatusForm(instance=company)
    return render(request,'controlcenter/business_detail.html',{'page_title':'Business overview','business':company,
        'members':Membership.objects.filter(company=company).select_related('user').order_by('role','user__username')[:60],
        'member_count':Membership.objects.filter(company=company).count(),
        'recent_sessions':HotspotSession.objects.filter(company=company).select_related('customer','plan','router')[:12],
        'routers_count':Router.objects.filter(company=company).count(),
        'plans_count':WifiPlan.objects.filter(company=company).count(),
        'customer_count':HotspotCustomer.objects.filter(company=company).count(),
        'sessions_count':HotspotSession.objects.filter(company=company).count(),
        'online_count':HotspotSession.objects.filter(company=company).filter(HotspotSession.online_filter()).count(),
        'vouchers_count':Voucher.objects.filter(company=company).count(),
        'sales_sum':ManualSale.objects.filter(company=company).aggregate(total=Sum('amount'))['total'] or 0,
        'can_manage_platform':platform_can_manage(request.user),'form':form})

@platform_required(manage=True)
@require_POST
@transaction.atomic
def business_update(request,pk):
    company=get_object_or_404(Company.objects.select_for_update(),pk=pk)
    form=CompanyStatusForm(request.POST,instance=company)
    if not form.is_valid():
        messages.error(request,'Please provide a valid status and subscription date.')
        return redirect('controlcenter:business_detail',pk=pk)
    old_status=company.status
    old_ends=company.subscription_ends
    updated=form.save()
    PlatformAudit.objects.create(actor=request.user,company=company,action='BUSINESS_ACCOUNT_UPDATED',
        note=f'Status: {old_status} → {updated.status}; subscription: {old_ends} → {updated.subscription_ends}')
    messages.success(request,'Business status updated and audit trail recorded.')
    return redirect('controlcenter:business_detail',pk=pk)

@platform_required()
def users(request):
    q=request.GET.get('q','').strip()[:120]
    kind=request.GET.get('kind','all')
    qs=User.objects.prefetch_related('company_memberships__company').order_by('-date_joined','-id')
    if q: qs=qs.filter(Q(username__icontains=q)|Q(email__icontains=q)|Q(first_name__icontains=q)|Q(last_name__icontains=q))
    if kind=='staff': qs=qs.filter(is_staff=True)
    if kind=='inactive': qs=qs.filter(is_active=False)
    if kind=='customers': qs=qs.filter(is_staff=False)
    return render(request,'controlcenter/users.html',{'page_title':'All user accounts',
        'records':Paginator(qs,25).get_page(request.GET.get('page')),'filter_q':q,'filter_kind':kind})

@platform_required()
def user_detail(request,pk):
    person=get_object_or_404(User,pk=pk)
    if person.is_staff:
        return redirect('controlcenter:staff_detail',pk=person.pk)
    return render(request,'controlcenter/user_detail.html',{'page_title':'User account','person':person,
        'members':Membership.objects.filter(user=person).select_related('company'),
        'can_manage_platform':platform_can_manage(request.user)})

@platform_required()
def audit(request):
    records=PlatformAudit.objects.select_related('company','actor')
    return render(request,'controlcenter/audit.html',{'page_title':'Platform audit trail',
        'records':Paginator(records,30).get_page(request.GET.get('page'))})


@platform_required(manage=True)
@require_POST
@transaction.atomic
def user_access_update(request,pk):
    person=get_object_or_404(User.objects.select_for_update(),pk=pk)
    if person.pk == request.user.pk or person.is_superuser or person.is_staff:
        messages.error(request,'Staff and superuser account changes must be handled securely in Django Admin.')
        return redirect('controlcenter:user_detail',pk=pk)
    target=request.POST.get('account_state')
    if target not in ('enable','disable'):
        messages.error(request,'Invalid account action.')
        return redirect('controlcenter:user_detail',pk=pk)
    before=person.is_active
    person.is_active=(target=='enable')
    person.save(update_fields=['is_active'])
    PlatformAudit.objects.create(actor=request.user,action='USER_ACCESS_UPDATED',
        note=f'Account #{person.pk}: {"enabled" if before else "disabled"} → {"enabled" if person.is_active else "disabled"}.')
    messages.success(request,'Account access updated and audit trail recorded.')
    return redirect('controlcenter:user_detail',pk=pk)

# ---- WorldLink internal operating console (no Django Admin required) ----
import hashlib
import secrets
from django.contrib.auth import get_user_model as _get_user_model
from django.http import Http404
from django.views.decorators.cache import never_cache
from tenants.models import Membership as _Membership
from cloud.models import PlatformBranding
from .models import AccessInvitation
from .services import issue_invitation, invitation_url, set_staff_role, staff_role, platform_staff_queryset
from .forms import (StaffInviteForm, InvitationPasswordForm, BusinessCreateForm,
                    BusinessOwnerInviteForm, MembershipAddForm, BrandingForm)


def _can_manage_staff(request, target):
    if not platform_can_manage(request.user) or target.pk == request.user.pk or target.is_superuser:
        return False
    return bool(request.user.is_superuser or staff_role(target) == 'SUPPORT')


@platform_required()
def team(request):
    query = request.GET.get('q', '').strip()[:120]
    records = platform_staff_queryset().prefetch_related('worldlink_invitations')
    if query:
        records = records.filter(Q(username__icontains=query) | Q(email__icontains=query) |
                                 Q(first_name__icontains=query) | Q(last_name__icontains=query))
    result = Paginator(records, 25).get_page(request.GET.get('page'))
    for person in result:
        person.wl_role = staff_role(person)
        person.can_edit = _can_manage_staff(request, person)
    return render(request, 'controlcenter/team.html', {'records': result, 'filter_q': query,
        'page_title': 'WorldLink team', 'can_manage_platform': platform_can_manage(request.user)})


@platform_required(manage=True)
@transaction.atomic
def staff_invite(request):
    form = StaffInviteForm(request.POST or None, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        first, _, last = data['name'].strip().partition(' ')
        person = User(username=data['email'], email=data['email'], first_name=first,
                      last_name=last, is_staff=True, is_active=False)
        person.set_unusable_password()
        person.save()
        set_staff_role(person, data['role'])
        invite, token = issue_invitation(person, request.user, AccessInvitation.Purpose.STAFF)
        request.session['wl_recent_invite'] = {
            'email': person.email, 'link': invitation_url(request, invite, token),
            'purpose': 'WorldLink team',
        }
        messages.success(request, 'Staff account created. Share the one-time setup link securely.')
        return redirect('controlcenter:invitation_created')
    return render(request, 'controlcenter/staff_invite.html', {
        'form': form, 'page_title': 'Invite WorldLink staff', 'can_choose_manager': request.user.is_superuser})


@platform_required()
@never_cache
def invitation_created(request):
    invitation = request.session.pop('wl_recent_invite', None)
    return render(request, 'controlcenter/invitation_created.html', {
        'invitation': invitation, 'page_title': 'Invitation details',
    })


@platform_required()
def staff_detail(request, pk):
    person = get_object_or_404(User, pk=pk, is_staff=True)
    return render(request, 'controlcenter/staff_detail.html', {
        'page_title': 'Team member', 'person': person, 'person_role': staff_role(person),
        'can_manage_target': _can_manage_staff(request, person),
        'invitation': AccessInvitation.objects.filter(user=person, purpose='STAFF').first(),
        'allow_manager_role': request.user.is_superuser,
    })


@platform_required(manage=True)
@require_POST
@transaction.atomic
def staff_update(request, pk):
    person = get_object_or_404(User.objects.select_for_update(), pk=pk, is_staff=True)
    if not _can_manage_staff(request, person):
        raise PermissionDenied('You cannot modify this WorldLink team account.')
    action = request.POST.get('action')
    previous_role = staff_role(person)
    if action == 'role':
        chosen = request.POST.get('role')
        if chosen not in ('SUPPORT', 'MANAGER') or (chosen == 'MANAGER' and not request.user.is_superuser):
            raise PermissionDenied('Only a WorldLink Super Admin can assign managers.')
        set_staff_role(person, chosen)
        PlatformAudit.objects.create(actor=request.user, action='STAFF_ROLE_CHANGED',
            note=f'Team account #{person.pk} role: {previous_role} -> {chosen}.')
        messages.success(request, 'Team permissions updated.')
    elif action == 'disable':
        person.is_active = False
        person.save(update_fields=['is_active'])
        AccessInvitation.objects.filter(user=person, accepted_at__isnull=True,
            revoked_at__isnull=True).update(revoked_at=timezone.now())
        PlatformAudit.objects.create(actor=request.user, action='STAFF_DISABLED',
            note=f'Team account #{person.pk} ({person.email}) disabled.')
        messages.success(request, 'Team account disabled and outstanding invitations revoked.')
    elif action == 'enable':
        if not person.has_usable_password():
            messages.error(request, 'Invite this staff member to set their password first.')
            return redirect('controlcenter:staff_detail', pk=person.pk)
        person.is_active = True
        person.save(update_fields=['is_active'])
        PlatformAudit.objects.create(actor=request.user, action='STAFF_ENABLED',
            note=f'Team account #{person.pk} ({person.email}) re-enabled.')
        messages.success(request, 'Team account enabled.')
    elif action == 'reinvite':
        if person.has_usable_password() or person.is_active:
            messages.error(request, 'Only unactivated accounts can be re-invited.')
            return redirect('controlcenter:staff_detail', pk=person.pk)
        invite, token = issue_invitation(person, request.user, AccessInvitation.Purpose.STAFF)
        request.session['wl_recent_invite'] = {
            'email': person.email, 'link': invitation_url(request, invite, token),
            'purpose': 'WorldLink team',
        }
        return redirect('controlcenter:invitation_created')
    else:
        messages.error(request, 'Invalid action.')
    return redirect('controlcenter:staff_detail', pk=person.pk)


@platform_required(manage=True)
@transaction.atomic
def business_create(request):
    form = BusinessCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        company = form.save()
        PlatformAudit.objects.create(actor=request.user, company=company, action='BUSINESS_CREATED',
            note=f'Business #{company.pk} created ({company.name}).')
        messages.success(request, 'Business created. Invite an owner to give someone access.')
        return redirect('controlcenter:business_detail', pk=company.pk)
    return render(request, 'controlcenter/business_create.html', {'form':form,
        'page_title':'Create a business'})


@platform_required(manage=True)
@transaction.atomic
def business_invite_owner(request, pk):
    company = get_object_or_404(Company, pk=pk)
    form = BusinessOwnerInviteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        first, _, last = form.cleaned_data['name'].strip().partition(' ')
        email = form.cleaned_data['email']
        person = User(username=email, email=email, first_name=first, last_name=last, is_active=False)
        person.set_unusable_password()
        person.save()
        _Membership.objects.create(company=company, user=person, role=_Membership.Role.OWNER)
        invite, token = issue_invitation(person, request.user, AccessInvitation.Purpose.BUSINESS, company)
        request.session['wl_recent_invite'] = {'email': person.email,
            'link': invitation_url(request, invite, token), 'purpose': f'Business owner · {company.name}'}
        messages.success(request, 'Owner created. Share the one-time account activation link securely.')
        return redirect('controlcenter:invitation_created')
    return render(request, 'controlcenter/owner_invite.html', {
        'form': form, 'page_title': 'Invite business owner', 'business': company,
    })


@platform_required(manage=True)
@require_POST
@transaction.atomic
def business_add_member(request, pk):
    company = get_object_or_404(Company.objects.select_for_update(), pk=pk)
    form = MembershipAddForm(request.POST)
    if form.is_valid():
        person = form.existing_user
        membership, created = _Membership.objects.get_or_create(
            company=company, user=person, defaults={'role':form.cleaned_data['role']})
        if not created:
            messages.error(request, 'This account already belongs to the business. No changes made.')
        else:
            PlatformAudit.objects.create(actor=request.user, company=company, action='BUSINESS_MEMBER_ADDED',
                note=f'User account #{person.pk} assigned as {membership.role}.')
            messages.success(request, 'Existing business account added.')
    else:
        messages.error(request, 'Unable to assign member: ' + '; '.join(str(e) for errs in form.errors.values() for e in errs))
    return redirect('controlcenter:business_detail', pk=pk)


@platform_required()
def branding(request):
    instance = PlatformBranding.objects.order_by('pk').first()
    form = BrandingForm(instance=instance)
    if not request.user.is_superuser:
        for field in form.fields.values():
            field.disabled = True
    return render(request, 'controlcenter/branding.html', {
        'form':form, 'page_title':'WorldLink branding', 'can_edit_branding':request.user.is_superuser,
    })


@platform_required()
@require_POST
@transaction.atomic
def branding_update(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Only the WorldLink owner can change platform branding.')
    instance = PlatformBranding.objects.select_for_update().order_by('pk').first()
    form = BrandingForm(request.POST, request.FILES, instance=instance)
    if form.is_valid():
        form.save()
        PlatformAudit.objects.create(actor=request.user, action='PLATFORM_BRANDING_UPDATED',
            note='WorldLink product identity/branding updated.')
        messages.success(request, 'Platform branding updated across login, console and favicon.')
    else:
        messages.error(request, 'Please review your branding form: ' + '; '.join(str(e) for errs in form.errors.values() for e in errs))
    return redirect('controlcenter:branding')


@never_cache
def accept_invitation(request, pk, token):
    """A secret, single-use activation link, usable without an existing login."""
    digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
    invitation = get_object_or_404(AccessInvitation.objects.select_related('user','company'), pk=pk)
    if (not secrets.compare_digest(digest, invitation.token_digest) or not invitation.is_pending
            or invitation.user.is_active or invitation.user.has_usable_password()):
        raise Http404('Invitation expired or already used.')
    form = InvitationPasswordForm(invitation.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            locked = AccessInvitation.objects.select_for_update().select_related('user').get(pk=invitation.pk)
            if (not secrets.compare_digest(digest, locked.token_digest) or not locked.is_pending
                    or locked.user.is_active or locked.user.has_usable_password()):
                raise Http404('Invitation expired or already used.')
            person = locked.user
            person.set_password(form.cleaned_data['new_password1'])
            person.is_active = True
            person.save(update_fields=['password','is_active'])
            locked.accepted_at = timezone.now()
            locked.save(update_fields=['accepted_at'])
            PlatformAudit.objects.create(actor=None, company=locked.company,
                action='INVITATION_ACCEPTED', note=f'Account #{person.pk} activated via {locked.purpose} invitation.')
        messages.success(request, 'Password set. You can now sign in securely.')
        return redirect('/login/?portal=' + ('staff' if invitation.purpose == 'STAFF' else 'business'))
    response = render(request, 'auth/accept_invitation.html', {
        'form':form, 'invitation':invitation,
        'portal_type':'staff' if invitation.purpose == 'STAFF' else 'business'})
    response['Cache-Control'] = 'no-store, private'
    response['Referrer-Policy'] = 'no-referrer'
    return response

@platform_required()
def platform_customers(request):
    """Read-only, explicitly global directory for authorized WorldLink staff."""
    query = request.GET.get('q', '').strip()[:120]
    company_id = request.GET.get('company', '')
    qs = HotspotCustomer.objects.select_related('company').order_by('-created_at', '-id')
    if query:
        qs = qs.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) |
                       Q(email__icontains=query) | Q(company__name__icontains=query))
    if company_id.isdecimal():
        qs = qs.filter(company_id=int(company_id))
    return render(request, 'controlcenter/platform_customers.html', {
        'page_title': 'Hotspot customers',
        'records': Paginator(qs, 30).get_page(request.GET.get('page')),
        'filter_q': query, 'filter_company': company_id,
        'companies': Company.objects.order_by('name').only('id', 'name'),
    })


@platform_required()
def platform_sessions(request):
    """No session is labelled connected unless real recent adapter data proves it."""
    query = request.GET.get('q', '').strip()[:120]
    company_id = request.GET.get('company', '')
    state = request.GET.get('state', 'all')
    qs = HotspotSession.objects.select_related('customer','company','router','plan').order_by('-started_at','-id')
    if query:
        qs = qs.filter(Q(username__icontains=query) | Q(mac_address__icontains=query) |
                       Q(customer__full_name__icontains=query) | Q(company__name__icontains=query) |
                       Q(router__name__icontains=query))
    if company_id.isdecimal():
        qs = qs.filter(company_id=int(company_id))
    if state == 'online':
        qs = qs.filter(HotspotSession.online_filter())
    elif state == 'demo':
        qs = qs.filter(source='DEMO')
    elif state == 'offline':
        qs = qs.exclude(HotspotSession.online_filter())
    return render(request, 'controlcenter/platform_sessions.html', {
        'page_title':'Platform sessions',
        'records': Paginator(qs, 30).get_page(request.GET.get('page')),
        'filter_q': query, 'filter_company': company_id, 'filter_state': state,
        'companies': Company.objects.order_by('name').only('id', 'name'),
    })


@platform_required()
def platform_payments(request):
    """Read-only platform audit view; no ability to confirm merchants' money."""
    from payments.models import PaymentOrder
    query = request.GET.get('q', '').strip()[:80]
    company_id = request.GET.get('company', '')
    status = request.GET.get('status', '')
    qs = PaymentOrder.objects.select_related('company', 'plan', 'method').order_by('-created_at')
    if query:
        qs = qs.filter(Q(reference__icontains=query) | Q(company__name__icontains=query))
    if company_id.isdecimal():
        qs = qs.filter(company_id=int(company_id))
    if status in PaymentOrder.Status.values:
        qs = qs.filter(status=status)
    return render(request, 'controlcenter/platform_payments.html', {
        'page_title':'Platform payments', 'records':Paginator(qs,30).get_page(request.GET.get('page')),
        'filter_q':query, 'filter_company':company_id, 'filter_status':status,
        'companies':Company.objects.order_by('name').only('id','name'),
    })
