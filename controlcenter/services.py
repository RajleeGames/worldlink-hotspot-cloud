"""Invitation lifecycle and least-privilege platform team roles."""
import hashlib
import secrets
from datetime import timedelta
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from .models import AccessInvitation, PlatformAudit


def staff_role(user):
    if user.is_superuser:
        return 'OWNER'
    if not user.is_staff:
        return None
    if user.has_perm('cloud.manage_platform_console'):
        return 'MANAGER'
    if user.has_perm('cloud.view_platform_console'):
        return 'SUPPORT'
    return 'UNASSIGNED'


def set_staff_role(user, role):
    """Only set the two console permissions; never grant broad Django model permissions."""
    if user.is_superuser:
        raise ValueError('Cannot change owner permissions here.')
    allowed = {'SUPPORT', 'MANAGER'}
    if role not in allowed:
        raise ValueError('Unknown WorldLink staff role.')
    permissions = Permission.objects.filter(content_type__app_label='cloud', content_type__model='platformbranding', codename__in=['view_platform_console', 'manage_platform_console'])
    user.user_permissions.remove(*permissions)
    selected = ['view_platform_console'] + (['manage_platform_console'] if role == 'MANAGER' else [])
    user.user_permissions.add(*permissions.filter(codename__in=selected))
    user.is_staff = True
    user.save(update_fields=['is_staff'])


def issue_invitation(user, actor, purpose, company=None, validity_hours=48):
    if user.is_active or user.has_usable_password():
        raise ValueError('Only unactivated accounts may receive an invitation.')
    if purpose not in AccessInvitation.Purpose.values:
        raise ValueError('Invalid invitation type.')
    now = timezone.now()
    AccessInvitation.objects.filter(user=user, accepted_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
    raw_token = secrets.token_urlsafe(36)
    invite = AccessInvitation.objects.create(
        user=user, purpose=purpose, company=company, created_by=actor,
        token_digest=hashlib.sha256(raw_token.encode('utf-8')).hexdigest(),
        expires_at=now + timedelta(hours=validity_hours),
    )
    PlatformAudit.objects.create(actor=actor, company=company,
        action='STAFF_INVITED' if purpose == 'STAFF' else 'BUSINESS_OWNER_INVITED',
        note=f'Invitation issued for account #{user.pk} ({user.email}); expires in {validity_hours}h.')
    return invite, raw_token


def invitation_url(request, invite, token):
    return request.build_absolute_uri(reverse('controlcenter:accept_invitation', args=[invite.pk, token]))


def platform_staff_queryset():
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(is_staff=True).order_by('-date_joined', '-id')
