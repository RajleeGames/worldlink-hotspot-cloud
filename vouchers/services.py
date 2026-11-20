"""Secure single-device redemption of business-sold WorldLink voucher codes.

These are NOT Omada's built-in vouchers and NOT EvPay merchant collections.
Only a staff-approved, physically online Omada AP can redeem a paid code.
"""

import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from payments.omada import OmadaError, _authorize_external_guest, normalize_mac
from tenants.models import Company
from .models import ManualSale, Voucher, VoucherRedemption


class VoucherError(ValueError):
    """Safe to show to a hotspot visitor; never contains internal API details."""


def approved_voucher_route(company, ap_mac, ssid):
    """Exact tenant/AP/SSID with independent staff voucher authorization.

    The older single-company pilot remains usable until transferred. Central
    onboarding alone, a submitted MAC or payment approval alone cannot unlock it.
    """
    from networks.models import OmadaDeviceObservation, OmadaOnboarding

    if (not settings.OMADA_LIVE_ENABLED or company.status == Company.Status.SUSPENDED
            or not all((settings.OMADA_CONTROLLER_URL, settings.OMADA_CONTROLLER_ID,
                        settings.OMADA_OPERATOR_NAME, settings.OMADA_OPERATOR_PASSWORD))):
        return False
    try:
        mac = normalize_mac(ap_mac)
    except ValueError:
        return False
    if (company.pk == settings.OMADA_PILOT_COMPANY_ID and settings.OMADA_AP_MAC
            and ssid == settings.OMADA_SSID):
        try:
            if mac == normalize_mac(settings.OMADA_AP_MAC):
                return True
        except ValueError:
            pass
    if company.status != Company.Status.ACTIVE or not ssid:
        return False
    # During cutover an EAP must not be authorized for both the legacy pilot
    # and a newly registered business. Explicitly retire its pilot gate first.
    if company.pk != settings.OMADA_PILOT_COMPANY_ID and settings.OMADA_AP_MAC:
        try:
            if mac == normalize_mac(settings.OMADA_AP_MAC):
                return False
        except ValueError:
            pass
    return OmadaOnboarding.objects.filter(
        router__company=company, router__family='OMADA',
        connection_mode=OmadaOnboarding.ConnectionMode.CENTRAL,
        status=OmadaOnboarding.Status.REVIEWED, reviewed_by__isnull=False,
        managed_site__company=company, managed_site__openapi_site_id__gt='',
        ap_mac__iexact=mac, ssid_name=ssid,
        voucher_access_approved_at__isnull=False,
        voucher_access_approved_by__isnull=False,
        router__omada_observation__state=OmadaDeviceObservation.State.CONNECTED,
    ).filter(
        router__omada_observation__checked_at__gte=timezone.now() - timedelta(seconds=120),
        router__omada_observation__checked_at__lte=timezone.now(),
    ).exists()


def _validate_session(company, context):
    if not context or not approved_voucher_route(company, context.get('apMac'), context.get('ssidName')):
        raise VoucherError('Connect to this business Wi-Fi and reopen its login page.')
    captured_at = context.get('capturedAt')
    if not isinstance(captured_at, int) or not 0 <= time.time() - captured_at <= 600:
        raise VoucherError('Your Wi-Fi login session expired. Reconnect and try again.')
    try:
        normalize_mac(context['clientMac'])
        normalize_mac(context['apMac'])
        if context['radioId'] not in (0, 1) or not context['clientIp']:
            raise ValueError('Invalid radio or IP')
    except (KeyError, TypeError, ValueError):
        raise VoucherError('Reconnect to the hotspot to verify your device.') from None


def redeem_voucher(*, company, raw_code, context):
    """Claim code atomically, then contact Omada outside DB transaction.

    Concurrent redemption and cross-device replays never grant a second device.
    An uncertain API result is retried only for the original device and within
    the original fixed expiry; Redis/IP throttle is enforced at the HTTP edge.
    """
    _validate_session(company, context)
    code = str(raw_code or '').strip().upper()
    if not (8 <= len(code) <= 24 and code.startswith('WHC-')):
        raise VoucherError('Enter a valid WorldLink voucher code.')
    now = timezone.now()
    with transaction.atomic():
        voucher = Voucher.objects.select_for_update().select_related('batch__plan').filter(
            company=company, code=code,
        ).first()
        if (voucher is None or voucher.status != Voucher.Status.SOLD or
                not ManualSale.objects.filter(voucher=voucher, company=company).exists()):
            raise VoucherError('This code is unavailable. Ask the business to verify the sale.')
        redemption = VoucherRedemption.objects.select_for_update().filter(voucher=voucher).first()
        if redemption is None:
            redemption = VoucherRedemption.objects.create(
                company=company, voucher=voucher,
                client_mac=context['clientMac'], client_ip=context['clientIp'],
                ap_mac=context['apMac'], ssid_name=context['ssidName'],
                radio_id=context['radioId'],
                claimed_at=now,
                expires_at=now + timedelta(minutes=voucher.batch.plan.duration_minutes),
            )
        elif (redemption.company_id != company.pk or redemption.client_mac != context['clientMac']
              or redemption.ap_mac != context['apMac'] or redemption.ssid_name != context['ssidName']):
            raise VoucherError('This voucher has already been assigned to a different device.')
        if redemption.expires_at <= now:
            raise VoucherError('This voucher has expired. Please buy a new one.')
        if redemption.trying_until and redemption.trying_until > now:
            raise VoucherError('Activation is processing. Please wait a moment and retry.')
        redemption.client_ip = context['clientIp']
        redemption.radio_id = context['radioId']
        redemption.trying_until = now + timedelta(seconds=40)
        redemption.last_error = ''
        redemption.save(update_fields=['client_ip', 'radio_id', 'trying_until', 'last_error'])

    try:
        # Re-check immediately before the external operation: revocation or AP
        # disconnection between claim and send must fail closed.
        _validate_session(company, context)
        remaining_ms = int((redemption.expires_at - timezone.now()).total_seconds() * 1000)
        _authorize_external_guest(
            client_mac=redemption.client_mac, client_ip=context['clientIp'],
            ap_mac=redemption.ap_mac, ssid_name=redemption.ssid_name,
            radio_id=context['radioId'], plan=voucher.batch.plan, remaining_ms=remaining_ms,
        )
    except (OmadaError, VoucherError):
        VoucherRedemption.objects.filter(pk=redemption.pk).update(
            trying_until=None, last_error='Controller access is not confirmed. Please retry shortly.',
        )
        raise VoucherError('Could not confirm internet access. Try again shortly or ask the business for help.') from None

    VoucherRedemption.objects.filter(pk=redemption.pk).update(
        trying_until=None, activated_at=redemption.activated_at or timezone.now(), last_error='',
    )
    return redemption
