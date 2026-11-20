from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('networks', '0005_omada_central_sites'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='omadaonboarding', name='live_payments_approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='omadaonboarding', name='live_payments_approved_by',
            field=models.ForeignKey(blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='approved_omada_live_payment_routers', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='omadaonboarding', name='live_payments_note',
            field=models.CharField(blank=True, max_length=400),
        ),
    ]
