from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from tenants.models import Company
from networks.models import WifiPlan
from portal.models import CaptivePortal
from payments.models import PaymentMethod


class Command(BaseCommand):
    help = 'Create SAMPLE packages and a cash-at-counter method for local portal development only.'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', required=True, type=int)
        parser.add_argument('--confirm', action='store_true')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('This command is disabled when DEBUG=False.')
        if not options['confirm']:
            raise CommandError('Include --confirm to create demo records in this local business.')
        company = Company.objects.filter(pk=options['company_id']).first()
        if not company:
            raise CommandError('No company with that ID.')
        portal, created = CaptivePortal.objects.get_or_create(company=company)
        if not portal.enabled:
            portal.enabled = True
            portal.save(update_fields=['enabled'])
        for name, minutes, price in [('Demo - One Hour', 60, 500), ('Demo - Three Hours', 180, 1000), ('Demo - One Day', 1440, 2000)]:
            WifiPlan.objects.get_or_create(company=company, name=name, defaults={'duration_minutes': minutes, 'price': price})
        PaymentMethod.objects.get_or_create(company=company, channel='CASH', label='DEMO - Pay at counter', defaults={
            'is_active': True,
            'instructions': 'Test only: Do not send real money. Business staff can manually review requests.',
        })
        self.stdout.write(self.style.SUCCESS(f'Local demo ready at /wifi/{company.slug}/. No router or payment API is connected.'))
