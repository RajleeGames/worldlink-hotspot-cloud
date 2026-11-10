from django.db import migrations, models
import django.db.models.deletion
import django.core.validators

class Migration(migrations.Migration):
    initial = True
    dependencies = [('tenants', '0001_initial')]
    operations = [migrations.CreateModel(name='CaptivePortal', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('enabled', models.BooleanField(default=False, help_text='Public page only. Turning this on does not activate internet access.')),
        ('headline_en', models.CharField(default='Connect to our Wi-Fi', max_length=120)),
        ('headline_sw', models.CharField(default='Unganisha Wi-Fi yetu', max_length=120)),
        ('subtitle_en', models.CharField(default='Choose a package and request access.', max_length=220)),
        ('subtitle_sw', models.CharField(default='Chagua kifurushi na omba huduma.', max_length=220)),
        ('accent_color', models.CharField(default='#1677b8', max_length=7, validators=[django.core.validators.RegexValidator('^#[0-9a-fA-F]{6}$', 'Use a six-digit hex color such as #1677b8.')])),
        ('support_phone', models.CharField(blank=True, max_length=30)),
        ('terms', models.TextField(blank=True, help_text='Shown on the public portal. Do not include passwords or sensitive account information.', max_length=1000)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='captive_portal', to='tenants.company')),
    ])]
