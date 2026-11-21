# WorldLink monthly platform subscriptions: separate from customer Wi-Fi collections.
import uuid
from decimal import Decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0004_evpaycompanyauthorization'),
        ('tenants', '0002_company_logo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformSubscriptionPayment',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('reference', models.CharField(unique=True, max_length=40)),
                ('amount', models.DecimalField(default=Decimal('20000.00'), max_digits=12, decimal_places=2)),
                ('currency', models.CharField(default='TZS', max_length=3)),
                ('phone', models.CharField(max_length=15)),
                ('operator', models.CharField(max_length=20, choices=[('Mpesa','M-Pesa'), ('AirtelMoney','Airtel Money'),('TigoPesa','Mixx by Yas / Tigo Pesa'),('HaloPesa','HaloPesa')])),
                ('environment', models.CharField(max_length=10)),
                ('status', models.CharField(max_length=12, default='CREATED', choices=[('CREATED','Created'),('UNKNOWN','Checking payment'),('PENDING','Pending'),('PROCESSING','Processing'),('ON-HOLD','On hold'),('SUCCESS','Paid'),('SETTLED','Settled'),('FAILED','Failed'),('REFUNDED','Refunded'),('REVERSED','Reversed')])),
                ('transaction_id', models.CharField(blank=True, max_length=100)),
                ('fsp_reference', models.CharField(blank=True, max_length=100)),
                ('confirmed_at', models.DateTimeField(null=True, blank=True)),
                ('applied_at', models.DateTimeField(null=True, blank=True)),
                ('period_starts', models.DateField(null=True, blank=True)),
                ('period_ends', models.DateField(null=True, blank=True)),
                ('last_checked_at', models.DateTimeField(null=True, blank=True)),
                ('last_error', models.CharField(blank=True, max_length=250)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(to='tenants.company', related_name='platform_subscriptions',on_delete=django.db.models.deletion.PROTECT)),
                ('created_by', models.ForeignKey(to=settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=django.db.models.deletion.SET_NULL)),
            ],
            options={'ordering':['-created_at']},
        ),
        migrations.CreateModel(
            name='PlatformSubscriptionDelivery',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('delivery_id', models.CharField(unique=True,max_length=100)),
                ('event', models.CharField(max_length=40)),
                ('status', models.CharField(max_length=12)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('payment', models.ForeignKey(to='payments.platformsubscriptionpayment',related_name='deliveries',on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.AddConstraint(
            model_name='platformsubscriptionpayment',
            constraint=models.UniqueConstraint(fields=['transaction_id'],
                condition=~models.Q(transaction_id=''), name='wlsubs_unique_provider_txn'),
        ),
    ]
