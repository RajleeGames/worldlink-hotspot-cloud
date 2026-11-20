from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('networks', '0001_initial'),
        ('vouchers', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='router', name='address',
            field=models.GenericIPAddressField(
                blank=True, null=True,
                help_text='Router management IP reachable from this server over your private LAN/VPN.',
            ),
        ),
        migrations.AddField(
            model_name='router', name='management_port',
            field=models.PositiveIntegerField(
                default=443, validators=[MinValueValidator(1)],
                help_text='RouterOS HTTPS REST port (normally 443). Never expose it publicly.',
            ),
        ),
        migrations.AddField(
            model_name='router', name='last_checked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='RouterVoucherSync',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('synced_at', models.DateTimeField(auto_now_add=True)),
                ('router', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='voucher_syncs', to='networks.router')),
                ('voucher', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='router_syncs', to='vouchers.voucher')),
                ('synced_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='routervouchersync',
            constraint=models.UniqueConstraint(fields=('router', 'voucher'), name='whc_one_voucher_per_router'),
        ),
    ]
