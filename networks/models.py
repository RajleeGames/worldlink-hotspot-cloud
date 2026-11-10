from django.db import models
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
    address = models.GenericIPAddressField(null=True, blank=True, help_text='Inventory only; no connection yet')
    serial = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return self.name

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
