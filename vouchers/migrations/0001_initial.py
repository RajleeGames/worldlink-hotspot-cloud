from django.conf import settings
from django.db import migrations,models
import django.db.models.deletion
import django.core.validators

class Migration(migrations.Migration):
    initial=True
    dependencies=[('tenants','0001_initial'),('networks','0001_initial'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='VoucherBatch',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('label',models.CharField(blank=True,max_length=120)),
            ('quantity',models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='voucher_batches',to='tenants.company')),
            ('created_by',models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='created_batches',to=settings.AUTH_USER_MODEL)),
            ('plan',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='voucher_batches',to='networks.wifiplan')),
        ],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='Voucher',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('code',models.CharField(max_length=24,unique=True)),
            ('status',models.CharField(choices=[('READY','Ready (not activated)'),('SOLD','Sold manually (not activated)'),('VOID','Voided')],default='READY',max_length=8)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('batch',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='vouchers',to='vouchers.voucherbatch')),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='vouchers',to='tenants.company')),
        ],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='ManualSale',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('amount',models.DecimalField(decimal_places=2,max_digits=12,validators=[django.core.validators.MinValueValidator(0)])),
            ('method',models.CharField(choices=[('CASH','Cash'),('BANK','Bank transfer'),('OTHER','Other manually verified')],max_length=8)),
            ('notes',models.CharField(blank=True,max_length=250)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='manual_sales',to='tenants.company')),
            ('recorded_by',models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),
            ('voucher',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='manual_sale',to='vouchers.voucher')),
        ],options={'ordering':['-created_at']}),
    ]
