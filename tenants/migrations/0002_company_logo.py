import cloud.models
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('tenants', '0001_initial')]
    operations = [migrations.AddField(model_name='company', name='logo', field=models.ImageField(blank=True, upload_to='branding/businesses/', validators=[cloud.models.validate_brand_image], help_text='Your company logo (max 2 MB).'))]
