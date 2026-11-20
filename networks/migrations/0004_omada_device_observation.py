from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('networks', '0003_omada_onboarding')]

    operations = [
        migrations.CreateModel(
            name='OmadaDeviceObservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.CharField(choices=[('CONNECTED', 'Connected'), ('OFFLINE', 'Offline'), ('NOT_FOUND', 'AP not found'), ('UNKNOWN', 'Status not recognized'), ('ERROR', 'Controller unavailable')], default='UNKNOWN', max_length=12)),
                ('reported_status', models.CharField(blank=True, max_length=60)),
                ('checked_at', models.DateTimeField()),
                ('router', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='omada_observation', to='networks.router')),
            ],
        ),
    ]
