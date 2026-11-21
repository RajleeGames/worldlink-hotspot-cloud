"""Read-only subscription reconciliation; never sends a new USSD charge."""
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from payments.models import PlatformSubscriptionPayment
from payments.evpay import EvPayError
from payments.platform_subscription import retrieve_and_apply_subscription


class Command(BaseCommand):
    help = 'Reconcile pending/settling WorldLink subscription payments; no new charges.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=25)
        parser.add_argument('--loop', action='store_true')
        parser.add_argument('--interval', type=int, default=20)

    def handle(self, *args, **options):
        if not settings.EVPAY_ENABLED:
            self.stdout.write('EvPay not enabled; subscription polling skipped.')
            return
        if not options['loop']:
            self.run_batch(max(1, min(100, options['limit'])))
            return
        interval = max(10, min(120, options['interval']))
        while True:
            close_old_connections()
            self.run_batch(max(1, min(100, options['limit'])))
            close_old_connections()
            time.sleep(interval)

    def run_batch(self, limit):
        now = timezone.now()
        qs = PlatformSubscriptionPayment.objects.filter(environment=settings.EVPAY_ENVIRONMENT).filter(
            Q(status__in=('CREATED','UNKNOWN','PENDING','PROCESSING','ON-HOLD')) |
            Q(status='SUCCESS',created_at__gte=now-timedelta(days=14)) |
            Q(status='SETTLED',created_at__gte=now-timedelta(days=7))
        ).order_by('last_checked_at','created_at')[:limit]
        for payment in qs:
            try:
                retrieve_and_apply_subscription(payment)
            except (EvPayError, ValueError, LookupError, OSError) as exc:
                # Never turn an uncertain status into FAILED; callback may arrive later.
                payment.last_checked_at = timezone.now()
                payment.last_error = 'Unable to verify provider status. Will recheck original reference.'
                payment.save(update_fields=['last_checked_at','last_error'])
                self.stderr.write(f'Subscription #{payment.pk}: verification pending.')
        self.stdout.write(f'Checked {len(qs)} subscription reference(s).')
