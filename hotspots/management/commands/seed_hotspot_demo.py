"""Explicit, idempotent DEMO-only session fixtures; never genuine online users."""
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from tenants.models import Company
from networks.models import Router, WifiPlan
from hotspots.models import HotspotCustomer, HotspotSession

class Command(BaseCommand):
    help='Create clearly marked DEMO-only hotspot customers and sessions (never count as online).'

    def add_arguments(self,parser):
        parser.add_argument('--company-id',type=int,required=True)
        parser.add_argument('--count',type=int,default=24)
        parser.add_argument('--confirm',action='store_true')

    @transaction.atomic
    def handle(self,*args,**opts):
        if not opts['confirm']: raise CommandError('Use --confirm to explicitly create demo records.')
        count=opts['count']
        if not 1 <= count <= 250: raise CommandError('--count must be between 1 and 250.')
        company=Company.objects.filter(pk=opts['company_id']).first()
        if not company: raise CommandError('Company does not exist.')
        routers=list(Router.objects.filter(company=company).order_by('pk'))
        plans=list(WifiPlan.objects.filter(company=company).order_by('pk'))
        if not routers or not plans: raise CommandError('Create at least one router and Wi-Fi package first.')
        added=0
        for i in range(1,count+1):
            customer,_=HotspotCustomer.objects.get_or_create(company=company,full_name=f'DEMO Customer {i:03}',defaults={'notes':'Demonstration record only; not a real Wi-Fi customer.'})
            if HotspotSession.objects.filter(company=company,customer=customer,source='DEMO',username=f'DEMO-{i:04}').exists(): continue
            plan=plans[(i-1)%len(plans)]
            router=routers[(i-1)%len(routers)]
            started=timezone.now()-timedelta(minutes=(i*13)%370)
            expiration=started+timedelta(minutes=plan.duration_minutes)
            is_ended=(i%4==0)
            HotspotSession.objects.create(company=company,customer=customer,router=router,plan=plan,
                username=f'DEMO-{i:04}',mac_address=f'02:11:22:{(i//100)%256:02X}:{i%256:02X}:{(i*7)%256:02X}',
                source='DEMO',status='ENDED' if is_ended else 'ACTIVE',
                started_at=started,expires_at=expiration,
                ended_at=started+timedelta(minutes=min(30,plan.duration_minutes)) if is_ended else None,
                bytes_download=106954752*(i%7+1), bytes_upload=10485760*(i%5+1))
            added+=1
        self.stdout.write(self.style.SUCCESS(f'{added} new DEMO sessions created; genuine online count remains 0.'))
