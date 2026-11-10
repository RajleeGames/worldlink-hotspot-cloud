from django.db import migrations, models
import cloud.models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(name='PlatformBranding', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('name', models.CharField(default='WORLDLINK SECURITY SYSTEMS', max_length=120)),
        ('product_name', models.CharField(default='WorldLink Hotspot Cloud', max_length=120)),
        ('tagline', models.CharField(default='Linking Security to Every Corner!', max_length=180)),
        ('logo', models.ImageField(blank=True, upload_to='branding/platform/', validators=[cloud.models.validate_brand_image], help_text='PNG/JPG/WebP/GIF, up to 2 MB. Used for login, platform sidebar and favicon.')),
    ], options={'verbose_name': 'Platform branding', 'verbose_name_plural': 'Platform branding'})]
