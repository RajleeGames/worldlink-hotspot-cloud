from django.conf import settings
from django.urls import reverse
from tenants.utils import active_membership
from .models import PlatformBranding
from controlcenter.auth import platform_can_view
from controlcenter.services import staff_role

def build_breadcrumbs(request):
    resolver = getattr(request, 'resolver_match', None)
    if not resolver:
        return []
    name, namespace = resolver.url_name, resolver.namespace
    trail = [('Dashboard', 'cloud:dashboard')]
    if namespace == 'networks':
        lookup = {
            'routers': ('Routers','networks:routers'),
            'router_new': ('Routers','networks:routers','Add router'),
            'router_edit': ('Routers','networks:routers','Edit router'),
            'locations': ('Locations','networks:locations'),
            'location_new': ('Locations','networks:locations','Add location'),
            'location_edit': ('Locations','networks:locations','Edit location'),
            'plans': ('Wi-Fi packages','networks:plans'),
            'plan_new': ('Wi-Fi packages','networks:plans','New package'),
            'plan_edit': ('Wi-Fi packages','networks:plans','Edit package'),
        }
        trail.append(('Network', None))
        item = lookup.get(name)
        if item:
            trail.append((item[0], item[1] if len(item)>2 else None))
            if len(item)>2:
                trail.append((item[2],None))
    elif namespace == 'hotspots':
        trail.append(('Network', None))
        group='Connected users' if name in ('sessions','sessions_export','session_detail') else 'Wi-Fi customers'
        trail.append((group, ('hotspots:sessions' if group=='Connected users' else 'hotspots:customers') if name not in ('sessions','customers') else None))
        if name=='session_detail': trail.append(('Session details',None))
        if name=='customer_detail': trail.append(('Customer details',None))
        if name=='customer_edit': trail.append(('Edit customer',None))
        if name=='customer_new': trail.append(('New customer',None))
    elif namespace == 'controlcenter':
        trail=[('WorldLink Control Center','controlcenter:overview' if name!='overview' else None)]
        section_map = {
            'businesses':('All businesses','controlcenter:businesses'),
            'business_create':('Create a business',None),
            'business_detail':('All businesses','controlcenter:businesses'),
            'business_update':('All businesses','controlcenter:businesses'),
            'business_invite_owner':('All businesses','controlcenter:businesses'),
            'business_add_member':('All businesses','controlcenter:businesses'),
            'users':('All user accounts','controlcenter:users'),
            'user_detail':('All user accounts','controlcenter:users'),
            'user_access_update':('All user accounts','controlcenter:users'),
            'platform_customers':('Hotspot customers',None),
            'platform_sessions':('Platform sessions',None),
            'team':('WorldLink team','controlcenter:team'),
            'staff_invite':('WorldLink team','controlcenter:team'),
            'staff_detail':('WorldLink team','controlcenter:team'),
            'staff_update':('WorldLink team','controlcenter:team'),
            'invitation_created':('WorldLink team','controlcenter:team'),
            'branding':('Platform branding',None),
            'branding_update':('Platform branding',None),
            'audit':('Audit trail',None),
            'platform_payments':('Platform payments',None),
        }
        if name in section_map:
            label, url = section_map[name]
            trail.append((label, url if name not in ('businesses','users','team') else None))
        if name in ('business_detail','business_update','business_invite_owner','business_add_member'):
            trail.append(('Business details' if name!='business_invite_owner' else 'Invite owner',None))
        if name in ('user_detail','user_access_update','staff_detail','staff_update'):
            trail.append(('Account details',None))
        if name=='staff_invite': trail.append(('Invite staff',None))
        if name=='invitation_created': trail.append(('Invitation link',None))
    elif namespace == 'payments':
        trail.append(('Sales', None))
        if name in ('evpay_lab','evpay_auth','evpay_start','evpay_reconcile'):
            trail.append(('EvPay test lab', None))
        elif name in ('methods','method_create','method_edit','method_disable'):
            trail.append(('Payment methods','payments:methods' if name != 'methods' else None))
            if name == 'method_create': trail.append(('Add method',None))
            if name == 'method_edit': trail.append(('Edit method',None))
        else:
            trail.append(('Payment requests','payments:orders' if name != 'orders' else None))
            if name in ('order_detail','verify','cancel'): trail.append(('Request details',None))
    elif namespace == 'portal':
        trail.append(('Administration',None))
        trail.append(('Captive portal',None))
    elif namespace == 'vouchers':
        trail.append(('Sales', None))
        trail.append(('Voucher batches', 'vouchers:batches' if name != 'batches' else None))
        if name == 'create': trail.append(('Generate vouchers',None))
        elif name == 'batch_detail': trail.append(('View batch',None))
        elif name == 'batch_edit': trail.extend([('View batch',reverse('vouchers:batch_detail',kwargs={'pk':resolver.kwargs['pk']})),('Edit batch',None)])
    elif name in ('reports','expenses','expense_new','expense_edit'):
        trail.append(('Sales',None))
        if name == 'reports': trail.append(('Sales reports',None))
        else:
            trail.append(('Expenses','cloud:expenses' if name != 'expenses' else None))
            if name in ('expense_new','expense_edit'):
                trail.append(('Add expense' if name=='expense_new' else 'Edit expense',None))
    elif namespace == 'tenants':
        trail.append(('Administration',None))
        trail.append(('Business settings' if name=='settings' else 'Switch business',None))
    elif name == 'profile':
        trail.extend([('Administration',None),('My profile',None)])
    if name == 'dashboard':
        return [{'label':'Dashboard','url':None}]
    return [{'label':label,'url':(url if url.startswith('/') else reverse(url)) if url else None} for label,url in trail]

def shell_context(request):
    membership=active_membership(request)
    return {
        'active_membership':membership,
        'breadcrumbs':build_breadcrumbs(request) if request.user.is_authenticated else [],
        'active_company':membership.company if membership else None,
        'evpay_pilot_available': bool(membership and settings.EVPAY_ENABLED and settings.EVPAY_COMPANY_ID == membership.company_id),
        'ui_lang':request.session.get('ui_lang','en'),
        'allow_signup':settings.ALLOW_PUBLIC_SIGNUP,
        'platform_brand':PlatformBranding.objects.first(),
        'can_view_platform':platform_can_view(request.user),
        'platform_role_label':{'OWNER':'Super Admin','MANAGER':'Platform Manager','SUPPORT':'Support Staff','UNASSIGNED':'Platform Staff'}.get(staff_role(request.user),'Business User') if request.user.is_authenticated else 'Guest',
    }
