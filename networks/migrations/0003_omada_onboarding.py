from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('networks', '0002_mikrotik_pilot'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OmadaOnboarding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('connection_mode', models.CharField(choices=[('VPN', 'I have a private HTTPS/VPN controller address'), ('ASSISTED', 'Help me connect my controller securely')], default='ASSISTED', max_length=12)),
                ('controller_origin', models.URLField(blank=True, help_text='HTTPS VPN origin only, no /hotspot.html, credentials, or public port forwarding.', max_length=255)),
                ('controller_id', models.CharField(blank=True, help_text='Copy only the omadacId value from Omada’s URL, not the entire URL or a password.', max_length=80)),
                ('ap_mac', models.CharField(blank=True, help_text='Access point MAC, for example B8-FB-B3-79-B5-60.', max_length=17)),
                ('ssid_name', models.CharField(blank=True, help_text='Exact guest Wi-Fi name, including capitalization.', max_length=64)),
                ('setup_notes', models.TextField(blank=True, help_text='Optional details for WorldLink. Never include router or operator passwords.')),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('SUBMITTED', 'Awaiting WorldLink review'), ('NEEDS_INFO', 'More information needed'), ('REVIEWED', 'Details reviewed — connection pending')], default='DRAFT', max_length=12)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_note', models.CharField(blank=True, max_length=400)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('router', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='omada_onboarding', to='networks.router')),
            ],
            options={'ordering': ['-updated_at']},
        ),
    ]
