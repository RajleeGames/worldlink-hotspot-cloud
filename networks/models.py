from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from tenants.models import Company

class Location(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='locations')
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company','name'], name='unique_company_location')]
    def __str__(self):
        return self.name

class Router(models.Model):
    class Family(models.TextChoices):
        MIKROTIK = 'MIKROTIK', 'MikroTik'
        OMADA = 'OMADA', 'TP-Link Omada'
        OTHER = 'OTHER', 'Other / planned'
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='routers')
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='routers')
    name = models.CharField(max_length=120)
    family = models.CharField(max_length=12, choices=Family.choices, default=Family.MIKROTIK)
    model_name = models.CharField(max_length=100, blank=True)
    address = models.GenericIPAddressField(
        null=True, blank=True,
        help_text='Router management IP reachable from this server over your private LAN/VPN.',
    )
    management_port = models.PositiveIntegerField(
        default=443, validators=[MinValueValidator(1)],
        help_text='RouterOS HTTPS REST port (normally 443). Never expose it publicly.',
    )
    last_checked_at = models.DateTimeField(null=True, blank=True)
    serial = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return self.name


class OmadaOnboarding(models.Model):
    """Per-router setup request. Never grants access to a controller by itself.

    Credentials are deliberately not stored here. Only the already-approved
    single-company pilot in payments.omada can authorize paid clients.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Awaiting WorldLink review'
        NEEDS_INFO = 'NEEDS_INFO', 'More information needed'
        REVIEWED = 'REVIEWED', 'Details reviewed — connection pending'

    class ConnectionMode(models.TextChoices):
        VPN = 'VPN', 'I have a private HTTPS/VPN controller address'
        ASSISTED = 'ASSISTED', 'Help me connect my controller securely'

    router = models.OneToOneField(Router, on_delete=models.CASCADE, related_name='omada_onboarding')
    connection_mode = models.CharField(max_length=12, choices=ConnectionMode.choices, default=ConnectionMode.ASSISTED)
    controller_origin = models.URLField(max_length=255, blank=True, help_text='HTTPS VPN origin only, no /hotspot.html, credentials, or public port forwarding.')
    controller_id = models.CharField(max_length=80, blank=True, help_text='Copy only the omadacId value from Omada’s URL, not the entire URL or a password.')
    ap_mac = models.CharField(max_length=17, blank=True, help_text='Access point MAC, for example B8-FB-B3-79-B5-60.')
    ssid_name = models.CharField(max_length=64, blank=True, help_text='Exact guest Wi-Fi name, including capitalization.')
    setup_notes = models.TextField(blank=True, help_text='Optional details for WorldLink. Never include router or operator passwords.')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    review_note = models.CharField(max_length=400, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.router.name}: {self.get_status_display()}'

class WifiPlan(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='wifi_plans')
    name = models.CharField(max_length=120)
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    download_kbps = models.PositiveIntegerField(default=2048, validators=[MinValueValidator(1)])
    upload_kbps = models.PositiveIntegerField(default=1024, validators=[MinValueValidator(1)])
    data_limit_mb = models.PositiveIntegerField(null=True, blank=True)
    device_limit = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return self.name


class RouterVoucherSync(models.Model):
    """Proven RouterOS provisioning for a previously sold, paid-manually voucher."""
    router = models.ForeignKey(Router, on_delete=models.PROTECT, related_name='voucher_syncs')
    voucher = models.ForeignKey('vouchers.Voucher', on_delete=models.PROTECT, related_name='router_syncs')
    synced_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['router', 'voucher'], name='whc_one_voucher_per_router')
        ]
