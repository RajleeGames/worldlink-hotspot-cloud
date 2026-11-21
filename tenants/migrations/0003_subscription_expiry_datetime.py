"""Maintain exact subscription expiry time; preserve legacy end dates as end-of-day."""
from datetime import datetime, time
from zoneinfo import ZoneInfo
from django.db import migrations, models
from django.utils import timezone


def migrate_dates(apps, schema_editor):
    Company = apps.get_model('tenants', 'Company')
    tz = ZoneInfo('Africa/Dar_es_Salaam')
    for company in Company.objects.exclude(subscription_ends__isnull=True).iterator():
        if company.subscription_expires_at is None:
            company.subscription_expires_at = timezone.make_aware(
                datetime.combine(company.subscription_ends, time(23, 59, 59)), tz)
            company.save(update_fields=['subscription_expires_at'])


class Migration(migrations.Migration):
    dependencies = [('tenants', '0002_company_logo')]
    operations = [
        migrations.AddField(model_name='company', name='subscription_expires_at',
                            field=models.DateTimeField(null=True, blank=True)),
        migrations.RunPython(migrate_dates, migrations.RunPython.noop),
    ]
