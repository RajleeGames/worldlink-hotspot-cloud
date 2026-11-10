from django.conf import settings
from django.db import models

class PlatformAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    company = models.ForeignKey('tenants.Company',on_delete=models.SET_NULL,null=True,blank=True,related_name='platform_audits')
    action = models.CharField(max_length=80)
    note = models.CharField(max_length=400)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at','-id']
        indexes=[models.Index(fields=['created_at'],name='whc_audit_created_idx')]
    def __str__(self): return f'{self.action} • {self.created_at}'

class AccessInvitation(models.Model):
    """One-use invitation; only a SHA-256 digest is kept, never its URL token."""
    class Purpose(models.TextChoices):
        STAFF = 'STAFF', 'WorldLink staff'
        BUSINESS = 'BUSINESS', 'Business owner'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='worldlink_invitations')
    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    company = models.ForeignKey('tenants.Company', null=True, blank=True, on_delete=models.CASCADE)
    token_digest = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='issued_worldlink_invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['user', 'purpose'], name='whc_invite_user_type_idx')]

    @property
    def is_pending(self):
        from django.utils import timezone
        return not self.accepted_at and not self.revoked_at and self.expires_at > timezone.now()
