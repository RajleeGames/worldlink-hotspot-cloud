from django.db import migrations,models
import django.db.models.deletion
import django.core.validators

class Migration(migrations.Migration):
    initial=True
    dependencies=[('tenants','0001_initial')]
    operations=[
        migrations.CreateModel(name='Location',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('name',models.CharField(max_length=120)),
            ('address',models.CharField(blank=True,max_length=250)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='locations',to='tenants.company')),
        ]),
        migrations.CreateModel(name='WifiPlan',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('name',models.CharField(max_length=120)),
            ('duration_minutes',models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
            ('price',models.DecimalField(decimal_places=2,max_digits=12,validators=[django.core.validators.MinValueValidator(0)])),
            ('download_kbps',models.PositiveIntegerField(default=2048,validators=[django.core.validators.MinValueValidator(1)])),
            ('upload_kbps',models.PositiveIntegerField(default=1024,validators=[django.core.validators.MinValueValidator(1)])),
            ('data_limit_mb',models.PositiveIntegerField(blank=True,null=True)),
            ('device_limit',models.PositiveSmallIntegerField(default=1,validators=[django.core.validators.MinValueValidator(1)])),
            ('is_active',models.BooleanField(default=True)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='wifi_plans',to='tenants.company')),
        ],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='Router',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('name',models.CharField(max_length=120)),
            ('family',models.CharField(choices=[('MIKROTIK','MikroTik'),('OMADA','TP-Link Omada'),('OTHER','Other / planned')],default='MIKROTIK',max_length=12)),
            ('model_name',models.CharField(blank=True,max_length=100)),
            ('address',models.GenericIPAddressField(blank=True,help_text='Inventory only; no connection yet',null=True)),
            ('serial',models.CharField(blank=True,max_length=120)),
            ('notes',models.TextField(blank=True)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='routers',to='tenants.company')),
            ('location',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='routers',to='networks.location')),
        ],options={'ordering':['-created_at']}),
        migrations.AddConstraint(model_name='location',constraint=models.UniqueConstraint(fields=('company','name'),name='unique_company_location')),
    ]
