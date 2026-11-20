from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('networks', '0004_omada_device_observation')]

    operations = [
        migrations.CreateModel(
            name='OmadaManagedSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('inform_site_id', models.CharField(max_length=80, unique=True)),
                ('openapi_site_id', models.CharField(blank=True, max_length=80)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                              related_name='omada_managed_sites', to='tenants.company')),
            ],
            options={'ordering': ['company_id', 'name']},
        ),
        migrations.AddConstraint(
            model_name='omadamanagedsite',
            constraint=models.UniqueConstraint(
                fields=('openapi_site_id',), condition=~models.Q(openapi_site_id=''),
                name='whc_omada_unique_openapi_site',
            ),
        ),
        migrations.AlterField(
            model_name='omadaonboarding', name='connection_mode',
            field=models.CharField(
                choices=[
                    ('CENTRAL', 'Connect to WorldLink central Omada (recommended)'),
                    ('VPN', 'I have a private HTTPS/VPN controller address'),
                    ('ASSISTED', 'Help me connect my controller securely'),
                ], default='CENTRAL', max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='omadaonboarding', name='managed_site',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='approved_router_requests', to='networks.omadamanagedsite'),
        ),
    ]
