"""Tenant-only presentation of real controller sightings and paid entitlements."""
from datetime import timedelta

from django.utils import timezone

from payments.collections import EARNING_STATUSES
from payments.models import EvPayCollection
from vouchers.models import VoucherRedemption

from .models import OmadaClientObservation


def live_omada_clients(company, *, query='', router_id=None):
    """No synthetic connections and no guest identity inferred from a MAC."""
    now = timezone.now()
    qs = OmadaClientObservation.objects.filter(
        company=company, router__company=company,
        observed_at__gte=now-timedelta(seconds=120),
    ).select_related('router', 'router__omada_observation',
                     'router__omada_onboarding', 'router__omada_onboarding__managed_site')
    if router_id:
        qs = qs.filter(router_id=router_id)
    if query:
        from django.db.models import Q
        qs = qs.filter(Q(mac_address__icontains=query) | Q(ip_address__icontains=query)
                       | Q(device_type__icontains=query))
    result = []
    for observation in qs.order_by('-observed_at')[:250]:
        if not observation.online:
            continue
        payment = next((p for p in EvPayCollection.objects.filter(
            company=company, client_mac=observation.mac_address, ap_mac=observation.router.omada_onboarding.ap_mac,
            ssid_name=observation.ssid_name, status__in=EARNING_STATUSES,
            confirmed_at__isnull=False, omada_activated_at__isnull=False,
        ).select_related('plan').order_by('-confirmed_at')[:8]
            if p.confirmed_at + timedelta(minutes=p.plan.duration_minutes) > now), None)
        voucher = VoucherRedemption.objects.filter(
            company=company, client_mac=observation.mac_address,
            ap_mac=observation.router.omada_onboarding.ap_mac,
            ssid_name=observation.ssid_name, activated_at__isnull=False,
            expires_at__gt=now,
        ).select_related('voucher__batch__plan').order_by('-expires_at').first()
        expiry = None
        package = ''
        name = ''
        phone = ''
        source = ''
        if payment:
            expiry = payment.confirmed_at + timedelta(minutes=payment.plan.duration_minutes)
            package = payment.plan.name
            name = payment.customer_name
            phone = payment.phone
            source = 'EvPay'
        if voucher and (expiry is None or voucher.expires_at > expiry):
            expiry = voucher.expires_at
            package = voucher.voucher.batch.plan.name
            name = ''
            phone = ''
            source = 'Voucher'
        result.append({'device': observation, 'name': name, 'phone': phone,
                       'package': package, 'source': source, 'expires_at': expiry})
    return result
