"""Exact times for subscription periods, retaining legacy date fields for reports."""
from datetime import datetime, time
from zoneinfo import ZoneInfo
from django.db import migrations, models
from django.utils import timezone


def migrate_period_dates(apps, schema_editor):
    Payment = apps.get_model('payments', 'PlatformSubscriptionPayment')
    tz = ZoneInfo('Africa/Dar_es_Salaam')
    for payment in Payment.objects.exclude(applied_at__isnull=True).iterator():
        fields = []
        if payment.period_starts and not payment.period_started_at:
            payment.period_started_at = timezone.make_aware(datetime.combine(payment.period_starts, time.min), tz)
            fields.append('period_started_at')
        if payment.period_ends and not payment.period_expires_at:
            payment.period_expires_at = timezone.make_aware(datetime.combine(payment.period_ends, time(23, 59, 59)), tz)
            fields.append('period_expires_at')
        if fields:
            payment.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [('payments', '0005_platform_subscriptions'),
                    ('tenants', '0003_subscription_expiry_datetime')]
    operations = [
        migrations.AddField(model_name='platformsubscriptionpayment', name='period_started_at',
                            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='platformsubscriptionpayment', name='period_expires_at',
                            field=models.DateTimeField(null=True, blank=True)),
        migrations.RunPython(migrate_period_dates, migrations.RunPython.noop),
    ]
