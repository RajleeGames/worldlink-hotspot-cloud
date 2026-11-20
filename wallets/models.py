"""Platform-held collections only: never mix with tenant cash sales or EvPay test records."""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, F


class BusinessWallet(models.Model):
    company = models.OneToOneField('tenants.Company', on_delete=models.PROTECT, related_name='worldlink_wallet')
    collected = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    available = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    reserved = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    paid_out = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(collected__gte=0), name='whc_wallet_collected_nonneg'),
            models.CheckConstraint(condition=Q(available__gte=0), name='whc_wallet_available_nonneg'),
            models.CheckConstraint(condition=Q(reserved__gte=0), name='whc_wallet_reserved_nonneg'),
            models.CheckConstraint(condition=Q(paid_out__gte=0), name='whc_wallet_paid_nonneg'),
            models.CheckConstraint(condition=Q(collected=F('available') + F('reserved') + F('paid_out')), name='whc_wallet_balanced'),
        ]

    def __str__(self):
        return f'WorldLink funds · {self.company.name}'


class SettledCollection(models.Model):
    """One independently verified bank/provider settlement, never a test payment."""
    wallet = models.ForeignKey(BusinessWallet, on_delete=models.PROTECT, related_name='collections')
    source_reference = models.CharField(max_length=100, unique=True)
    settlement_reference = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='confirmed_hotspot_collections')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']


class WithdrawalDestination(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Needs verification'
        VERIFIED = 'VERIFIED', 'Verified by WorldLink'
        REJECTED = 'REJECTED', 'Rejected'

    company = models.ForeignKey('tenants.Company', on_delete=models.PROTECT, related_name='withdrawal_destinations')
    provider = models.CharField(max_length=15, choices=[
        ('MPESA', 'M-Pesa'), ('AIRTEL', 'Airtel Money'), ('MIXX', 'Mixx by Yas'), ('HALO', 'HaloPesa'),
    ])
    phone = models.CharField(max_length=12)
    account_name = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_hotspot_destinations')
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='verified_hotspot_destinations')
    verification_note = models.CharField(max_length=250, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        # Preserve rejected number/name attempts for audit while permitting corrected resubmission.
        constraints = [models.UniqueConstraint(fields=['company', 'provider', 'phone'],
            condition=Q(status__in=['PENDING', 'VERIFIED']), name='whc_unique_active_withdraw_number')]

    @property
    def masked_phone(self):
        return self.phone[:5] + '••••' + self.phone[-3:] if len(self.phone) >= 9 else '••••'


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Awaiting WorldLink payment'
        PROCESSING = 'PROCESSING', 'WorldLink preparing payment'
        PAID = 'PAID', 'Paid manually'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled by owner'

    company = models.ForeignKey('tenants.Company', on_delete=models.PROTECT, related_name='withdrawal_requests')
    request_key = models.UUIDField(unique=True, editable=False)
    destination = models.ForeignKey(WithdrawalDestination, on_delete=models.PROTECT, related_name='withdrawals')
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    recipient_phone = models.CharField(max_length=12)
    recipient_name = models.CharField(max_length=120)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_hotspot_withdrawals')
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='processed_hotspot_withdrawals')
    processing_note = models.CharField(max_length=250, blank=True)
    payout_reference = models.CharField(max_length=100, blank=True, unique=True, null=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['status', 'created_at'], name='whc_withdraw_queue_idx')]

    @property
    def masked_phone(self):
        return self.recipient_phone[:5] + '••••' + self.recipient_phone[-3:]
