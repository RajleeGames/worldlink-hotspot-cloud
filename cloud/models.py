from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


def validate_brand_image(image):
    if image.size > 2 * 1024 * 1024:
        raise ValidationError('Logo must be 2 MB or smaller.')
    if getattr(image, 'width', 0) > 2048 or getattr(image, 'height', 0) > 2048:
        raise ValidationError('Logo dimensions must not exceed 2048 x 2048 pixels.')
    allowed = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
    if getattr(image, 'content_type', '') not in ('', *allowed):
        raise ValidationError('Upload a PNG, JPG, WebP or GIF logo (SVG is not supported).')


class PlatformBranding(models.Model):
    # This is one WorldLink-wide brand, not a business/customer setting.
    name = models.CharField(max_length=120, default='WORLDLINK SECURITY SYSTEMS')
    product_name = models.CharField(max_length=120, default='WorldLink Hotspot Cloud')
    tagline = models.CharField(max_length=180, default='Linking Security to Every Corner!')
    logo = models.ImageField(upload_to='branding/platform/', blank=True, validators=[validate_brand_image],
                             help_text='PNG/JPG/WebP/GIF, up to 2 MB. Used for login, platform sidebar and favicon.')

    class Meta:
        verbose_name = 'Platform branding'
        verbose_name_plural = 'Platform branding'
        permissions = [('view_platform_console','Can access WorldLink platform control center'), ('manage_platform_console','Can change WorldLink business account status')]

    def __str__(self):
        return self.product_name


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('EQUIPMENT', 'Equipment'), ('INTERNET', 'Internet / ISP'),
        ('POWER', 'Power'), ('MAINTENANCE', 'Maintenance'),
        ('TRANSPORT', 'Transport'), ('OTHER', 'Other'),
    ]
    company = models.ForeignKey('tenants.Company', on_delete=models.CASCADE, related_name='expenses')
    date = models.DateField()
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='OTHER')
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f'{self.description} - {self.amount}'
