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


class EvPayCollection(models.Model):
    """Real customer collection into WorldLink's *one* EvPay merchant account.

    Every entry belongs to exactly one business.  Provider-confirmed collections
    are displayed as earnings; they are NOT automatically withdrawable until
    WorldLink separately confirms funds have cleared.
    """

    class Status(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        PENDING = 'PENDING', 'Awaiting phone approval'
        UNKNOWN = 'UNKNOWN', 'Checking payment status'
        PROCESSING = 'PROCESSING', 'Processing'
        ON_HOLD = 'ON-HOLD', 'On hold'
        SUCCESS = 'SUCCESS', 'Payment confirmed'
        SETTLED = 'SETTLED', 'Settled at EvPay'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'
        REVERSED = 'REVERSED', 'Reversed'

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='evpay_collections')
    plan = models.ForeignKey(WifiPlan, on_delete=models.PROTECT, related_name='evpay_collections')
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    checkout_nonce = models.UUIDField(unique=True, editable=False)
    reference = models.CharField(max_length=40, unique=True, editable=False)
    customer_name = models.CharField(max_length=90)
    phone = models.CharField(max_length=15)
    operator = models.CharField(max_length=20, choices=EvPayTestPayment.OPERATOR_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(100)])
    environment = models.CharField(max_length=10)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATED)
    transaction_id = models.CharField(max_length=100, blank=True)
    fsp_reference = models.CharField(max_length=100, blank=True)
    last_error = models.CharField(max_length=250, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Captured from Omada's external captive-portal redirect, not user form.
    client_mac = models.CharField(max_length=24, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    ap_mac = models.CharField(max_length=24, blank=True)
    ssid_name = models.CharField(max_length=100, blank=True)
    radio_id = models.PositiveSmallIntegerField(null=True, blank=True)
    omada_activated_at = models.DateTimeField(null=True, blank=True)
    omada_last_error = models.CharField(max_length=250, blank=True)
    omada_claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['company', 'status', 'created_at'], name='evpay_live_company_status')]
        constraints = [models.UniqueConstraint(fields=['transaction_id'],
            condition=~models.Q(transaction_id=''), name='evpay_live_unique_txn')]


class EvPayCollectionDelivery(models.Model):
    """Delivery idempotency and audit, separate from the isolated EvPay lab."""

    collection = models.ForeignKey(EvPayCollection, on_delete=models.PROTECT, related_name='deliveries')
    delivery_id = models.CharField(max_length=100, unique=True)
    event = models.CharField(max_length=40)
    status = models.CharField(max_length=12)
    received_at = models.DateTimeField(auto_now_add=True)


class EvPayCompanyAuthorization(models.Model):
    """WorldLink-only approval for collecting on behalf of one business.

    An explicit row overrides the legacy environment allowlist in either
    direction; this permits revocation from the web console without a deploy.
    """
    company = models.OneToOneField(Company, on_delete=models.PROTECT,
                                   related_name='evpay_authorization')
    enabled = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.company} · {"authorized" if self.enabled else "blocked"}'


# WorldLink platform subscriptions are separate from Wi-Fi business collection wallets.
from decimal import Decimal


class PlatformSubscriptionPayment(models.Model):
    class Status(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        UNKNOWN = 'UNKNOWN', 'Checking payment'
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        ON_HOLD = 'ON-HOLD', 'On hold'
        SUCCESS = 'SUCCESS', 'Paid'
        SETTLED = 'SETTLED', 'Settled'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'
        REVERSED = 'REVERSED', 'Reversed'

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='platform_subscriptions')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reference = models.CharField(max_length=40, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('20000.00'))
    currency = models.CharField(max_length=3, default='TZS')
    phone = models.CharField(max_length=15)
    operator = models.CharField(max_length=20, choices=EvPayTestPayment.OPERATOR_CHOICES)
    environment = models.CharField(max_length=10)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATED)
    transaction_id = models.CharField(max_length=100, blank=True)
    fsp_reference = models.CharField(max_length=100, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    abandoned_at = models.DateTimeField(null=True, blank=True)
    period_starts = models.DateField(null=True, blank=True)
    period_ends = models.DateField(null=True, blank=True)
    period_started_at = models.DateTimeField(null=True, blank=True)
    period_expires_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['transaction_id'],
                        condition=~models.Q(transaction_id=''), name='wlsubs_unique_provider_txn')]


class PlatformSubscriptionDelivery(models.Model):
    payment = models.ForeignKey(PlatformSubscriptionPayment, on_delete=models.PROTECT, related_name='deliveries')
    delivery_id = models.CharField(max_length=100, unique=True)
    event = models.CharField(max_length=40)
    status = models.CharField(max_length=12)
    received_at = models.DateTimeField(auto_now_add=True)
