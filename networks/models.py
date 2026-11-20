from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
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


class OmadaManagedSite(models.Model):
    """WorldLink-assigned central-controller site, never editable by tenants.

    The inform ID is from Omada's device-inform URL. Open API uses a separate
    site ID; the two must not be assumed equal.
    """

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='omada_managed_sites')
    name = models.CharField(max_length=120)
    inform_site_id = models.CharField(max_length=80, unique=True)
    openapi_site_id = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['company_id', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['openapi_site_id'],
                condition=~models.Q(openapi_site_id=''),
                name='whc_omada_unique_openapi_site',
            ),
        ]

    @property
    def inform_url(self):
        """Only WorldLink's explicitly configured hostname is ever published."""
        import re
        host = getattr(settings, 'OMADA_CENTRAL_INFORM_HOST', '')
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', host):
            return ''
        if not re.fullmatch(r'[0-9a-fA-F]{16,64}', self.inform_site_id):
            return ''
        return f'omada://{host}?dPort=29810&mPort=29814&omadacId={self.inform_site_id}'

    def __str__(self):
        return f'{self.company.name}: {self.name}'


class OmadaOnboarding(models.Model):
    """Per-router setup request. Never grants access to a controller by itself.

    Credentials are deliberately not stored here. Independent, staff-only
    financial approval is required before a new business can sell live access.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Awaiting WorldLink review'
        NEEDS_INFO = 'NEEDS_INFO', 'More information needed'
        REVIEWED = 'REVIEWED', 'Details reviewed — connection pending'

    class ConnectionMode(models.TextChoices):
        CENTRAL = 'CENTRAL', 'Connect to WorldLink central Omada (recommended)'
        VPN = 'VPN', 'I have a private HTTPS/VPN controller address'
        ASSISTED = 'ASSISTED', 'Help me connect my controller securely'

    router = models.OneToOneField(Router, on_delete=models.CASCADE, related_name='omada_onboarding')
    connection_mode = models.CharField(max_length=12, choices=ConnectionMode.choices, default=ConnectionMode.CENTRAL)
    managed_site = models.ForeignKey(
        OmadaManagedSite, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_router_requests',
    )
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
    live_payments_approved_at = models.DateTimeField(null=True, blank=True)
    live_payments_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_omada_live_payment_routers',
    )
    live_payments_note = models.CharField(max_length=400, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.router.name}: {self.get_status_display()}'


class OmadaDeviceObservation(models.Model):
    """Last read-only controller observation; NOT authorization to sell Wi-Fi."""

    class State(models.TextChoices):
        CONNECTED = 'CONNECTED', 'Connected'
        OFFLINE = 'OFFLINE', 'Offline'
        NOT_FOUND = 'NOT_FOUND', 'AP not found'
        UNKNOWN = 'UNKNOWN', 'Status not recognized'
        ERROR = 'ERROR', 'Controller unavailable'

    router = models.OneToOneField(Router, on_delete=models.CASCADE, related_name='omada_observation')
    state = models.CharField(max_length=12, choices=State.choices, default=State.UNKNOWN)
    reported_status = models.CharField(max_length=60, blank=True)
    checked_at = models.DateTimeField()

    @property
    def is_fresh(self):
        """Never present an old controller observation as a current online AP."""
        if not self.checked_at or not 0 <= (timezone.now() - self.checked_at).total_seconds() <= 120:
            return False
        from payments.omada import normalize_mac
        profile = getattr(self.router, 'omada_onboarding', None)
        if (self.router.family != Router.Family.OMADA or not profile
                or profile.status != OmadaOnboarding.Status.REVIEWED or not profile.reviewed_by_id):
            return False
        if profile.connection_mode == OmadaOnboarding.ConnectionMode.CENTRAL:
            return bool(profile.managed_site_id and profile.managed_site.company_id == self.router.company_id
                        and profile.managed_site.openapi_site_id and profile.ap_mac and profile.ssid_name)
        if (not settings.OMADA_LIVE_ENABLED or self.router.company_id != settings.OMADA_PILOT_COMPANY_ID
                or profile.connection_mode != OmadaOnboarding.ConnectionMode.VPN
                or profile.controller_origin.rstrip('/') != settings.OMADA_CONTROLLER_URL.rstrip('/')
                or profile.controller_id != settings.OMADA_CONTROLLER_ID
                or profile.ssid_name != settings.OMADA_SSID):
            return False
        try:
            return normalize_mac(profile.ap_mac) == normalize_mac(settings.OMADA_AP_MAC)
        except ValueError:
            return False

    def __str__(self):
        return f'{self.router.name}: {self.state}'

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
