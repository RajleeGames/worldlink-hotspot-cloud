from django.core.validators import RegexValidator
from django.db import models
from tenants.models import Company


class CaptivePortal(models.Model):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='captive_portal')
    enabled = models.BooleanField(default=False, help_text='Public page only. Turning this on does not activate internet access.')
    headline_en = models.CharField(max_length=120, default='Connect to our Wi-Fi')
    headline_sw = models.CharField(max_length=120, default='Unganisha Wi-Fi yetu')
    subtitle_en = models.CharField(max_length=220, default='Choose a package and request access.')
    subtitle_sw = models.CharField(max_length=220, default='Chagua kifurushi na omba huduma.')
    accent_color = models.CharField(max_length=7, default='#1677b8', validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Use a six-digit hex color such as #1677b8.')])
    support_phone = models.CharField(max_length=30, blank=True)
    terms = models.TextField(max_length=1000, blank=True, help_text='Shown on the public portal. Do not include passwords or sensitive account information.')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Portal: {self.company.name}'
