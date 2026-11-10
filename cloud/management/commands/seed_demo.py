"""Opt-in development-only sample data; never seed a production database."""
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from tenants.models import Company, Membership
from networks.models import Location, Router, WifiPlan
from vouchers.models import VoucherBatch, Voucher, ManualSale
from vouchers.views import secure_code

class Command(BaseCommand):
    help = 'Create one clearly labelled demo business for an existing user (DEBUG only).'
    def add_arguments(self,parser):
        parser.add_argument('--email',required=True,help='Email address (username) of your existing user')
    def handle(self,*args,**options):
        if not settings.DEBUG:
            raise CommandError('Demo data is only allowed with DJANGO_DEBUG=True.')
        try:
            user=get_user_model().objects.get(username__iexact=options['email'].strip())
        except get_user_model().DoesNotExist:
            raise CommandError('Create this account first, then run seed_demo again.')
        with transaction.atomic():
            company,created=Company.objects.get_or_create(slug='worldlink-demo-business',defaults={'name':'DEMO • Kilimanjaro Guest Wi-Fi','city':'Moshi','status':Company.Status.TRIAL})
            if not created:
                raise CommandError('Demo business already exists; skipping to avoid duplicate data.')
            Membership.objects.create(company=company,user=user,role=Membership.Role.OWNER)
            downtown=Location.objects.create(company=company,name='DEMO • Moshi Main',address='Moshi town')
            garden=Location.objects.create(company=company,name='DEMO • Garden Zone',address='Kilimanjaro area')
            Router.objects.create(company=company,location=downtown,name='DEMO • Main Hotspot',family='MIKROTIK',model_name='RB750Gr3')
            Router.objects.create(company=company,location=garden,name='DEMO • Outdoor AP',family='OMADA',model_name='EAP110-Outdoor')
            Router.objects.create(company=company,location=garden,name='DEMO • Backup Wi-Fi',family='OTHER',model_name='Planning')
            plans=[('DEMO • 1 Hour',60,500),('DEMO • 24 Hours',1440,2000),('DEMO • 7 Days',10080,10000)]
            created_plans=[WifiPlan.objects.create(company=company,name=name,duration_minutes=duration,price=Decimal(amount),download_kbps=3000,upload_kbps=1000) for name,duration,amount in plans]
            batch=VoucherBatch.objects.create(company=company,plan=created_plans[1],label='DEMO • Sample front desk',quantity=24,created_by=user)
            for i in range(24):
                voucher=Voucher.objects.create(company=company,batch=batch,code=secure_code())
                if i < 5:
                    voucher.status=Voucher.Status.SOLD
                    voucher.save(update_fields=['status'])
                    ManualSale.objects.create(company=company,voucher=voucher,amount=created_plans[1].price,method=ManualSale.PaymentMethod.CASH,recorded_by=user,notes='DEMO SAMPLE ONLY')
        self.stdout.write(self.style.SUCCESS('Demo workspace created. Sign in and select it under Switch business. NO router or payment is connected.'))
