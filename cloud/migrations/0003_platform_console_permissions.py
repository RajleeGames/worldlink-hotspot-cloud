from django.db import migrations
class Migration(migrations.Migration):
    dependencies=[('cloud','0002_expense')]
    operations=[migrations.AlterModelOptions(name='platformbranding',options={
        'verbose_name':'Platform branding',
        'verbose_name_plural':'Platform branding',
        'permissions':[
            ('view_platform_console','Can access WorldLink platform control center'),
            ('manage_platform_console','Can change WorldLink business account status'),
        ],
    })]
