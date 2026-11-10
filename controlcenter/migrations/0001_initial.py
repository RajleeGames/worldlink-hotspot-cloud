from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
class Migration(migrations.Migration):
    initial = True
    dependencies=[('tenants','0002_company_logo'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[migrations.CreateModel(name='PlatformAudit',fields=[
        ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
        ('action',models.CharField(max_length=80)),('note',models.CharField(max_length=400)),
        ('created_at',models.DateTimeField(auto_now_add=True)),
        ('actor',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),
        ('company',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='platform_audits',to='tenants.company')),
    ],options={'ordering':['-created_at','-id'],'indexes':[models.Index(fields=['created_at'],name='whc_audit_created_idx')]})]
