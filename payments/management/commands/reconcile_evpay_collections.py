"""Read-only EvPay status polling fallback if a signed webhook is delayed.

The fast loop is deliberately a *pilot* fallback. Signed, push-driven provider
webhooks remain the preferred way to activate clients at larger scale.
"""
from datetime import timedelta
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, close_old_connections
from django.db.models import Q
from django.utils import timezone

from payments.collections import apply_collection_status
from payments.evpay import retrieve_ussd, EvPayError
from payments.models import EvPayCollection


class Command(BaseCommand):
    help = 'Safely check existing EvPay USSD references; NEVER initiate new charges.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=25)
        parser.add_argument('--fast', action='store_true',
                            help='Poll recent pending references with a short, rate-limited interval.')
        parser.add_argument('--loop', action='store_true',
                            help='Keep running as a supervised fast-reconciliation service.')
        parser.add_argument('--interval', type=int, default=5,
                            help='Seconds between loop iterations (2–30; default 5).')

    def handle(self, *args, **options):
        if not settings.EVPAY_ENABLED or not settings.EVPAY_PUBLIC_CHECKOUT_ENABLED:
            self.stdout.write('Customer collection pilot disabled. No requests.')
            return
        if not options['loop']:
            self._reconcile(options['limit'], fast=options['fast'])
            return
        interval = max(2, min(options['interval'], 30))
        while True:
            close_old_connections()
            self._reconcile(options['limit'], fast=True)
            close_old_connections()
            time.sleep(interval)

    def _reconcile(self, limit, *, fast):
        now = timezone.now()
        qs = EvPayCollection.objects.filter(
            company_id__in=settings.EVPAY_COLLECTION_COMPANY_IDS,
            environment=settings.EVPAY_ENVIRONMENT,
            status__in=('CREATED', 'UNKNOWN', 'PENDING', 'PROCESSING', 'ON-HOLD', 'SUCCESS', 'SETTLED'),
        )
        # SUCCESS is customer-paid, NOT merchant-settled (per EvPay API).
        # Revisit it automatically until SETTLED/reversed; re-check recent
        # SETTLED records occasionally for late reversals. Read only; this
        # never marks bank funds withdrawable or initiates new charges.
        pending = Q(status__in=('CREATED', 'UNKNOWN', 'PENDING', 'PROCESSING', 'ON-HOLD'))
        successful = Q(status='SUCCESS', created_at__gte=now-timedelta(days=14))
        settled = Q(status='SETTLED', created_at__gte=now-timedelta(days=7))
        if fast:
            # The first three minutes matter for customers waiting on Wi-Fi.
            # Bound API requests per reference; stale payments use a slower cadence.
            recent = now - timedelta(minutes=3)
            older = now - timedelta(minutes=15)
            first_attempt = Q(last_checked_at__isnull=True)
            rapid = (Q(created_at__lt=now - timedelta(seconds=3), created_at__gte=recent)
                     & (first_attempt | Q(last_checked_at__lt=now - timedelta(seconds=5))))
            medium = (Q(created_at__lt=recent, created_at__gte=older)
                      & (first_attempt | Q(last_checked_at__lt=now - timedelta(seconds=30))))
            slow = (Q(created_at__lt=older)
                    & (first_attempt | Q(last_checked_at__lt=now - timedelta(minutes=5))))
            waiting = pending & (rapid | medium | slow)
            confirm_settlement = successful & Q(created_at__lt=now-timedelta(minutes=1)) & (
                Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=now-timedelta(minutes=5)))
            late_reversal = settled & (Q(last_checked_at__isnull=True)
                                       | Q(last_checked_at__lt=now-timedelta(hours=1)))
            qs = qs.filter(waiting | confirm_settlement | late_reversal)
        else:
            qs = qs.filter(
                (pending | successful) & Q(created_at__lt=now-timedelta(minutes=1))
                & (Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=now-timedelta(minutes=5)))
                | settled & (Q(last_checked_at__isnull=True)
                             | Q(last_checked_at__lt=now-timedelta(hours=1))),
            )
        for item in qs.order_by('created_at')[:max(0, min(limit, 100))]:
            try:
                data = retrieve_ussd(item.reference)
                reference = data.get('customReference') or data.get('reference') or data.get('requestId')
                if reference != item.reference:
                    raise ValueError('Provider reference mismatch.')
                collection, _ = apply_collection_status(reference=item.reference,
                    status=data.get('status'), amount=data.get('amount'), currency=data.get('currency'),
                    transaction_id=data.get('transRef') or data.get('transactionId') or '',
                    fsp_reference=data.get('mnoRef') or data.get('fspReference') or '')
            except (EvPayError, ValueError, LookupError, IntegrityError):
                EvPayCollection.objects.filter(pk=item.pk).update(
                    last_checked_at=timezone.now(),
                    last_error='Provider status could not be verified. Retrying this reference later.')
                self.stderr.write(f'EvPay collection #{item.pk} not verified; will check later.')
            else:
                if collection.status == item.status:
                    continue
                self.stdout.write(f'EvPay collection #{item.pk} reconciled.')
