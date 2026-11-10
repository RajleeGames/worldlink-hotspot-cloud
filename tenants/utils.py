from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from .models import Membership

def active_membership(request):
    if not request.user.is_authenticated:
        return None
    memberships = Membership.objects.select_related('company').filter(user=request.user).order_by('id')
    selected = request.session.get('active_company_id')
    chosen = memberships.filter(company_id=selected).first() if selected else None
    return chosen or memberships.first()

def require_tenant(*roles):
    def decorator(func):
        @login_required
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            membership = active_membership(request)
            if not membership:
                from controlcenter.auth import platform_can_view
                return redirect('controlcenter:overview' if platform_can_view(request.user) else 'tenants:no_company')
            if membership.company.status == 'SUSPENDED':
                raise PermissionDenied('Business account is suspended.')
            if roles and membership.role not in roles:
                raise PermissionDenied('Your role does not allow this action.')
            request.active_membership = membership
            request.active_company = membership.company
            return func(request, *args, **kwargs)
        return wrapper
    return decorator
