from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='EvPayTestPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(editable=False, max_length=40, unique=True)),
                ('operator', models.CharField(choices=[('Mpesa', 'M-Pesa'), ('AirtelMoney', 'Airtel Money'), ('TigoPesa', 'Mixx by Yas / Tigo Pesa'), ('HaloPesa', 'HaloPesa')], max_length=20)),
                ('phone', models.CharField(max_length=15)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(100)])),
                ('environment', models.CharField(default='sandbox', max_length=10)),
                ('status', models.CharField(default='CREATED', max_length=14)),
                ('transaction_id', models.CharField(blank=True, max_length=100)),
                ('fsp_reference', models.CharField(blank=True, max_length=100)),
                ('last_error', models.CharField(blank=True, max_length=250)),
                ('last_checked_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='evpay_tests', to='tenants.company')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'indexes': [models.Index(fields=['company', 'created_at'], name='evpay_test_tenant_date')]},
        ),
        migrations.CreateModel(
            name='EvPayDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('delivery_id', models.CharField(max_length=100, unique=True)),
                ('event', models.CharField(max_length=40)),
                ('status', models.CharField(max_length=14)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='webhook_deliveries', to='payments.evpaytestpayment')),
            ],
        ),
    ]
