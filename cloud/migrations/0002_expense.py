from django.conf import settings
from django.db import migrations, models
import django.core.validators
import decimal
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('cloud', '0001_initial'),
        ('tenants', '0002_company_logo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name='Expense', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('date', models.DateField()),
            ('category', models.CharField(choices=[('EQUIPMENT','Equipment'),('INTERNET','Internet / ISP'),('POWER','Power'),('MAINTENANCE','Maintenance'),('TRANSPORT','Transport'),('OTHER','Other')], default='OTHER', max_length=15)),
            ('description', models.CharField(max_length=200)),
            ('amount', models.DecimalField(max_digits=12,decimal_places=2,validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))])),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='expenses',to='tenants.company')),
            ('recorded_by', models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['-date','-id']}),
    ]
