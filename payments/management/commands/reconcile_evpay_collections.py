"""Read-only EvPay status polling fallback if a signed webhook is delayed."""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from payments.collections import apply_collection_status
from payments.evpay import retrieve_ussd, EvPayError
from payments.models import EvPayCollection


class Command(BaseCommand):
    help = 'Safely check existing EvPay USSD references; NEVER initiate new charges.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=25)

    def handle(self, *args, **options):
        if not settings.EVPAY_ENABLED or not settings.EVPAY_PUBLIC_CHECKOUT_ENABLED:
            self.stdout.write('Customer collection pilot disabled. No requests.')
            return
        now = timezone.now()
        qs = EvPayCollection.objects.filter(
            company_id__in=settings.EVPAY_COLLECTION_COMPANY_IDS,
            environment=settings.EVPAY_ENVIRONMENT,
            status__in=('CREATED', 'UNKNOWN', 'PENDING', 'PROCESSING', 'ON-HOLD'),
            created_at__lt=now - timedelta(minutes=1),
        ).filter(Q(last_checked_at__isnull=True) |
                 Q(last_checked_at__lt=now - timedelta(minutes=5)))
        for item in qs.order_by('created_at')[:max(0, min(options['limit'], 100))]:
            try:
                data = retrieve_ussd(item.reference)
                reference = data.get('customReference') or data.get('reference') or data.get('requestId')
                if reference != item.reference:
                    raise ValueError('Provider reference mismatch.')
                apply_collection_status(reference=item.reference,
                    status=data.get('status'), amount=data.get('amount'), currency=data.get('currency'),
                    transaction_id=data.get('transRef') or data.get('transactionId') or '',
                    fsp_reference=data.get('mnoRef') or data.get('fspReference') or '')
            except (EvPayError, ValueError, LookupError, IntegrityError):
                EvPayCollection.objects.filter(pk=item.pk).update(
                    last_checked_at=timezone.now(),
                    last_error='Provider status could not be verified. Retrying this reference later.')
                self.stderr.write(f'EvPay collection #{item.pk} not verified; will check later.')
            else:
                self.stdout.write(f'EvPay collection #{item.pk} reconciled.')
