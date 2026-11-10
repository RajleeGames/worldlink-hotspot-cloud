from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from networks.models import WifiPlan
from tenants.models import Company

class VoucherBatch(models.Model):
    company = models.ForeignKey(Company,on_delete=models.CASCADE,related_name='voucher_batches')
    plan = models.ForeignKey(WifiPlan,on_delete=models.PROTECT,related_name='voucher_batches')
    label = models.CharField(max_length=120,blank=True)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,related_name='created_batches')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return f'Batch #{self.pk} ({self.quantity})'

class Voucher(models.Model):
    class Status(models.TextChoices):
        READY='READY','Ready (not activated)'
        SOLD='SOLD','Sold manually (not activated)'
        VOID='VOID','Voided'
    company = models.ForeignKey(Company,on_delete=models.CASCADE,related_name='vouchers')
    batch = models.ForeignKey(VoucherBatch,on_delete=models.CASCADE,related_name='vouchers')
    code = models.CharField(max_length=24,unique=True)
    status = models.CharField(max_length=8,choices=Status.choices,default=Status.READY)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return self.code

class ManualSale(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH='CASH','Cash'
        BANK='BANK','Bank transfer'
        OTHER='OTHER','Other manually verified'
    company = models.ForeignKey(Company,on_delete=models.CASCADE,related_name='manual_sales')
    voucher = models.OneToOneField(Voucher,on_delete=models.PROTECT,related_name='manual_sale')
    amount = models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(0)])
    method = models.CharField(max_length=8,choices=PaymentMethod.choices)
    notes = models.CharField(max_length=250,blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return f'{self.voucher.code} / {self.amount}'
