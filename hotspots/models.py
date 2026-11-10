"""Hotspot customers and session observations.

Never infer online status from a voucher sale or a demo record. A genuine online
reading needs a recent heartbeat from an authenticated RADIUS/Omada adapter.
"""
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class HotspotCustomer(models.Model):
    company = models.ForeignKey('tenants.Company', on_delete=models.CASCADE, related_name='hotspot_customers')
    full_name = models.CharField(max_length=140)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    notes = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name', 'id']
        indexes = [models.Index(fields=['company', 'full_name'], name='whc_customer_name_idx')]

    def __str__(self):
        return self.full_name


class HotspotSession(models.Model):
    class Source(models.TextChoices):
        DEMO = 'DEMO', 'Demo only'
        RADIUS = 'RADIUS', 'RADIUS adapter'
        OMADA = 'OMADA', 'Omada adapter'
        IMPORT = 'IMPORT', 'Imported history'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active / observed'
        ENDED = 'ENDED', 'Ended'
        DISCONNECTED = 'DISCONNECTED', 'Disconnected'
        EXPIRED = 'EXPIRED', 'Expired'

    company = models.ForeignKey('tenants.Company', on_delete=models.CASCADE, related_name='hotspot_sessions')
    customer = models.ForeignKey(HotspotCustomer, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    router = models.ForeignKey('networks.Router', on_delete=models.PROTECT, related_name='hotspot_sessions')
    plan = models.ForeignKey('networks.WifiPlan', on_delete=models.PROTECT, related_name='hotspot_sessions')
    voucher = models.ForeignKey('vouchers.Voucher', on_delete=models.SET_NULL, null=True, blank=True, related_name='hotspot_sessions')
    external_id = models.CharField(max_length=128, null=True, blank=True, help_text='Adapter-provided per-router session identifier')
    username = models.CharField(max_length=120, blank=True)
    mac_address = models.CharField(max_length=32, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.DEMO)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    bytes_download = models.PositiveBigIntegerField(default=0)
    bytes_upload = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at', '-id']
        indexes = [
            models.Index(fields=['company', 'started_at'], name='whc_session_started_idx'),
            models.Index(fields=['company', 'source', 'status', 'last_seen_at'], name='whc_session_status_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['company', 'router', 'external_id'], condition=Q(external_id__isnull=False), name='whc_unique_adapter_session'),
        ]

    def clean(self):
        super().clean()
        for name in ('router', 'plan', 'voucher', 'customer'):
            related_id = getattr(self, f'{name}_id', None)
            if not related_id or not self.company_id:
                continue
            obj = getattr(self, name)
            if obj.company_id != self.company_id:
                raise ValidationError({name: 'The record must belong to the same business.'})
        if self.expires_at and self.started_at and self.expires_at <= self.started_at:
            raise ValidationError({'expires_at': 'Expiry must be later than session start.'})
        if self.source == self.Source.DEMO and self.external_id:
            raise ValidationError({'external_id': 'Demo entries cannot use an adapter session identifier.'})

    @staticmethod
    def online_filter(now=None):
        now = now or timezone.now()
        return Q(source__in=['RADIUS', 'OMADA'], status='ACTIVE', last_seen_at__gte=now-timedelta(minutes=5), ended_at__isnull=True) & (Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    @property
    def online(self):
        now = timezone.now()
        return bool(self.source in (self.Source.RADIUS, self.Source.OMADA)
                    and self.status == self.Status.ACTIVE and not self.ended_at
                    and self.last_seen_at and self.last_seen_at <= now+timedelta(minutes=2) and self.last_seen_at >= now-timedelta(minutes=5)
                    and (self.expires_at is None or self.expires_at > now))

    @property
    def time_left_seconds(self):
        if not self.expires_at:
            return None
        return max(0, int((self.expires_at-timezone.now()).total_seconds()))

    @property
    def total_mb(self):
        return round((self.bytes_download+self.bytes_upload)/1048576, 1)

    def __str__(self):
        return f'{self.username or self.mac_address or self.pk} on {self.router.name}'
