from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def platform_can_view(user):
    return bool(user.is_authenticated and (user.is_superuser or (user.is_staff and user.has_perm('cloud.view_platform_console'))))


def platform_can_manage(user):
    return bool(platform_can_view(user) and (user.is_superuser or user.has_perm('cloud.manage_platform_console')))


def platform_required(manage=False):
    def decorator(func):
        @login_required(login_url='/login/?portal=staff')
        @wraps(func)
        def wrapper(request,*args,**kwargs):
            if not (platform_can_manage(request.user) if manage else platform_can_view(request.user)):
                raise PermissionDenied('WorldLink platform access is required.')
            return func(request,*args,**kwargs)
        return wrapper
    return decorator
