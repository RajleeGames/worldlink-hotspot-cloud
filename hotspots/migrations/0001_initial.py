from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q
import django.utils.timezone

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('tenants','0002_company_logo'),
        ('networks','0001_initial'),
        ('vouchers','0001_initial'),
    ]
    operations = [
        migrations.CreateModel(name='HotspotCustomer',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False,auto_created=True,verbose_name='ID')),
            ('full_name',models.CharField(max_length=140)),
            ('phone',models.CharField(blank=True,max_length=32)),
            ('email',models.EmailField(blank=True,max_length=254)),
            ('notes',models.CharField(blank=True,max_length=250)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('updated_at',models.DateTimeField(auto_now=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='hotspot_customers',to='tenants.company')),
        ],options={'ordering':['full_name','id'], 'indexes':[models.Index(fields=['company','full_name'],name='whc_customer_name_idx')]}),
        migrations.CreateModel(name='HotspotSession',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False,auto_created=True,verbose_name='ID')),
            ('external_id',models.CharField(blank=True,null=True,max_length=128,help_text='Adapter-provided per-router session identifier')),
            ('username',models.CharField(blank=True,max_length=120)),
            ('mac_address',models.CharField(blank=True,max_length=32)),
            ('ip_address',models.GenericIPAddressField(blank=True,null=True)),
            ('source',models.CharField(choices=[('DEMO','Demo only'),('RADIUS','RADIUS adapter'),('OMADA','Omada adapter'),('IMPORT','Imported history')],default='DEMO',max_length=10)),
            ('status',models.CharField(choices=[('ACTIVE','Active / observed'),('ENDED','Ended'),('DISCONNECTED','Disconnected'),('EXPIRED','Expired')],default='ACTIVE',max_length=16)),
            ('started_at',models.DateTimeField(default=django.utils.timezone.now)),
            ('expires_at',models.DateTimeField(blank=True,null=True)),
            ('last_seen_at',models.DateTimeField(blank=True,null=True)),
            ('ended_at',models.DateTimeField(blank=True,null=True)),
            ('bytes_download',models.PositiveBigIntegerField(default=0)),
            ('bytes_upload',models.PositiveBigIntegerField(default=0)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('updated_at',models.DateTimeField(auto_now=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='hotspot_sessions',to='tenants.company')),
            ('customer',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='sessions',to='hotspots.hotspotcustomer')),
            ('router',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='hotspot_sessions',to='networks.router')),
            ('plan',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='hotspot_sessions',to='networks.wifiplan')),
            ('voucher',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='hotspot_sessions',to='vouchers.voucher')),
        ],options={'ordering':['-started_at','-id'],'indexes':[
            models.Index(fields=['company','started_at'],name='whc_session_started_idx'),
            models.Index(fields=['company','source','status','last_seen_at'],name='whc_session_status_idx')],
            'constraints':[models.UniqueConstraint(fields=['company','router','external_id'],condition=Q(external_id__isnull=False),name='whc_unique_adapter_session')]}),
    ]
