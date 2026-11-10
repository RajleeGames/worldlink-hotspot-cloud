from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='Company',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('name',models.CharField(max_length=160)),
            ('slug',models.SlugField(max_length=190,unique=True)),
            ('email',models.EmailField(blank=True,max_length=254)),
            ('phone',models.CharField(blank=True,max_length=30)),
            ('city',models.CharField(blank=True,max_length=100)),
            ('status',models.CharField(choices=[('TRIAL','Trial'),('ACTIVE','Active'),('SUSPENDED','Suspended')],default='TRIAL',max_length=12)),
            ('subscription_ends',models.DateField(blank=True,null=True)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
        ]),
        migrations.CreateModel(name='Membership',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('role',models.CharField(choices=[('OWNER','Owner'),('MANAGER','Manager'),('CASHIER','Cashier'),('TECHNICIAN','Technician'),('VIEWER','Viewer')],default='VIEWER',max_length=15)),
            ('joined_at',models.DateTimeField(auto_now_add=True)),
            ('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='memberships',to='tenants.company')),
            ('user',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='company_memberships',to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddConstraint(model_name='membership',constraint=models.UniqueConstraint(fields=('company','user'),name='unique_company_user')),
    ]
