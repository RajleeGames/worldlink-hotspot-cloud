"""Run on the VPS every 15-30 seconds while the controller VPN is connected."""
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from payments.collections import EARNING_STATUSES
from payments.models import EvPayCollection
from payments.omada import authorize_paid_collection, OmadaError


class Command(BaseCommand):
    help = 'Authorize provider-confirmed WorldLink Wi-Fi purchases via private Omada API.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--loop', action='store_true', help='Keep checking for paid sessions (systemd service).')
        parser.add_argument('--interval', type=int, default=5, help='Seconds between checks in loop mode.')

    def handle(self, *args, **options):
        if not settings.OMADA_LIVE_ENABLED or not settings.EVPAY_PUBLIC_CHECKOUT_ENABLED:
            self.stdout.write('Omada live pilot disabled. No network changes.')
            return
        if options['loop']:
            interval = max(2, min(options['interval'], 60))
            while True:
                close_old_connections()
                self._activate(options['limit'])
                close_old_connections()
                time.sleep(interval)
        else:
            self._activate(options['limit'])

    def _activate(self, limit):
        now = timezone.now()
        old_claim = now - timedelta(minutes=3)
        rows = EvPayCollection.objects.filter(
            company_id=settings.OMADA_PILOT_COMPANY_ID,
            status__in=EARNING_STATUSES, omada_activated_at__isnull=True,
        ).filter(Q(omada_claimed_at__isnull=True) | Q(omada_claimed_at__lt=old_claim))
        for pk in rows.order_by('confirmed_at').values_list('pk', flat=True)[:max(0, min(limit, 50))]:
            claimed = EvPayCollection.objects.filter(pk=pk, omada_activated_at__isnull=True).filter(
                Q(omada_claimed_at__isnull=True) | Q(omada_claimed_at__lt=old_claim)).update(omada_claimed_at=now)
            if not claimed:
                continue
            collection = EvPayCollection.objects.select_related('plan').get(pk=pk)
            try:
                authorize_paid_collection(collection)
            except OmadaError as exc:
                EvPayCollection.objects.filter(pk=pk).update(
                    omada_last_error=str(exc)[:250], omada_claimed_at=None)
                self.stderr.write(f'Collection #{pk}: authorization pending; check secure controller connection.')
            else:
                EvPayCollection.objects.filter(pk=pk).update(
                    omada_activated_at=timezone.now(), omada_last_error='', omada_claimed_at=None)
                self.stdout.write(f'Collection #{pk}: authorized.')
