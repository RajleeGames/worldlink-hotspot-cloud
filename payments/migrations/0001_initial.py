import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('tenants', '0001_initial'),
        ('networks', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name='PaymentMethod', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('channel', models.CharField(max_length=10, choices=[('MPESA','M-Pesa'),('AIRTEL','Airtel Money'),('MIXX','Mixx by Yas'),('HALO','HaloPesa'),('BANK','Bank transfer'),('CASH','Cash at counter')])),
            ('label', models.CharField(max_length=90, help_text='Public-facing label, for example M-Pesa Lipa Namba.')),
            ('account_name', models.CharField(blank=True, help_text='Name shown to the payer.', max_length=120)),
            ('account_number', models.CharField(blank=True, help_text='Till, business number, phone or bank account. Never enter API secrets.', max_length=70)),
            ('instructions', models.TextField(blank=True, max_length=400)),
            ('is_active', models.BooleanField(default=False, help_text='Show manual instructions on the public portal. This does NOT connect a payment API.')),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_methods', to='tenants.company')),
        ], options={'ordering':['channel','id']}),
        migrations.CreateModel(name='PaymentOrder', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ('reference', models.CharField(editable=False, max_length=24, unique=True)),
            ('customer_name', models.CharField(max_length=90)),
            ('customer_phone', models.CharField(max_length=20)),
            ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
            ('currency', models.CharField(default='TZS', editable=False, max_length=3)),
            ('status', models.CharField(default='PENDING', max_length=12, choices=[('PENDING','Awaiting verification'),('PAID','Manually confirmed'),('CANCELLED','Cancelled')])),
            ('merchant_reference', models.CharField(blank=True, help_text='Reference checked in the merchant account/statement by an authorized user.', max_length=100)),
            ('review_note', models.CharField(blank=True, max_length=250)),
            ('verified_at', models.DateTimeField(blank=True, null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_orders', to='tenants.company')),
            ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_orders', to='networks.wifiplan')),
            ('method', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='payments.paymentmethod')),
            ('verified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verified_hotspot_orders', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering':['-created_at'], 'indexes':[models.Index(fields=['company','status','created_at'], name='pay_order_tenant_status_idx')]}),
        migrations.CreateModel(name='PaymentAudit', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('action', models.CharField(max_length=30)),
            ('comment', models.CharField(blank=True, max_length=250)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audit_entries', to='payments.paymentorder')),
        ], options={'ordering':['-created_at']}),
    ]
