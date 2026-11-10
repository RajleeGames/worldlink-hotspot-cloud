from django.conf import settings
from cloud.models import validate_brand_image
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

class Company(models.Model):
    class Status(models.TextChoices):
        TRIAL = 'TRIAL', 'Trial'
        ACTIVE = 'ACTIVE', 'Active'
        SUSPENDED = 'SUSPENDED', 'Suspended'
    name = models.CharField(max_length=160)
    logo = models.ImageField(upload_to='branding/businesses/', blank=True, validators=[validate_brand_image], help_text='Your company logo (max 2 MB).')
    slug = models.SlugField(max_length=190, unique=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIAL)
    subscription_ends = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            slug = slugify(self.name) or 'business'
            candidate, n = slug, 2
            while Company.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f'{slug}-{n}'
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        MANAGER = 'MANAGER', 'Manager'
        CASHIER = 'CASHIER', 'Cashier'
        TECHNICIAN = 'TECHNICIAN', 'Technician'
        VIEWER = 'VIEWER', 'Viewer'
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='company_memberships')
    role = models.CharField(max_length=15, choices=Role.choices, default=Role.VIEWER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'user'], name='unique_company_user')]
    def __str__(self):
        return f'{self.user} / {self.company} ({self.role})'
