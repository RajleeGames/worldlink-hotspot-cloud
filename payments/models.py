import uuid
from django.conf import settings
from django.core.validators import RegexValidator, MinValueValidator
from django.db import models
from tenants.models import Company
from networks.models import WifiPlan


class PaymentMethod(models.Model):
    class Channel(models.TextChoices):
        MPESA = 'MPESA', 'M-Pesa'
        AIRTEL = 'AIRTEL', 'Airtel Money'
        MIXX = 'MIXX', 'Mixx by Yas'
        HALO = 'HALO', 'HaloPesa'
        BANK = 'BANK', 'Bank transfer'
        CASH = 'CASH', 'Cash at counter'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payment_methods')
    channel = models.CharField(max_length=10, choices=Channel.choices)
    label = models.CharField(max_length=90, help_text='Public-facing label, for example M-Pesa Lipa Namba.')
    account_name = models.CharField(max_length=120, blank=True, help_text='Name shown to the payer.')
    account_number = models.CharField(max_length=70, blank=True, help_text='Till, business number, phone or bank account. Never enter API secrets.')
    instructions = models.TextField(blank=True, max_length=400)
    is_active = models.BooleanField(default=False, help_text='Show manual instructions on the public portal. This does NOT connect a payment API.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['channel', 'id']

    def __str__(self):
        return f'{self.label} · {self.company.name}'


class PaymentOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Awaiting verification'
        PAID = 'PAID', 'Manually confirmed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payment_orders')
    plan = models.ForeignKey(WifiPlan, on_delete=models.PROTECT, related_name='payment_orders')
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name='orders')
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    reference = models.CharField(max_length=24, unique=True, editable=False)
    customer_name = models.CharField(max_length=90)
    customer_phone = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='TZS', editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    merchant_reference = models.CharField(max_length=100, blank=True, help_text='Reference checked in the merchant account/statement by an authorized user.')
    review_note = models.CharField(max_length=250, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_hotspot_orders')
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['company', 'status', 'created_at'], name='pay_order_tenant_status_idx')]

    def __str__(self):
        return self.reference


class PaymentAudit(models.Model):
    order = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name='audit_entries')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=30)
    comment = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class EvPayTestPayment(models.Model):
    """Isolated payment gateway test; NEVER grants vouchers or network authorization."""
    OPERATOR_CHOICES = [
        ('Mpesa', 'M-Pesa'), ('AirtelMoney', 'Airtel Money'),
        ('TigoPesa', 'Mixx by Yas / Tigo Pesa'), ('HaloPesa', 'HaloPesa'),
    ]
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='evpay_tests')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reference = models.CharField(max_length=40, unique=True, editable=False)
    operator = models.CharField(max_length=20, choices=OPERATOR_CHOICES)
    phone = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(100)])
    environment = models.CharField(max_length=10, default='sandbox')
    status = models.CharField(max_length=14, default='CREATED')
    transaction_id = models.CharField(max_length=100, blank=True)
    fsp_reference = models.CharField(max_length=100, blank=True)
    last_error = models.CharField(max_length=250, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['company', 'created_at'], name='evpay_test_tenant_date')]

    def __str__(self):
        return self.reference


class EvPayDelivery(models.Model):
    """Webhook delivery de-duplication; no raw phone numbers or secrets persisted."""
    payment = models.ForeignKey(EvPayTestPayment, on_delete=models.CASCADE, related_name='webhook_deliveries')
    delivery_id = models.CharField(max_length=100, unique=True)
    event = models.CharField(max_length=40)
    status = models.CharField(max_length=14)
    received_at = models.DateTimeField(auto_now_add=True)
