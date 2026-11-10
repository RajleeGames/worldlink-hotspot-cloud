"""Integration boundary for trusted RADIUS/Omada accounting adapters.

Not wired to public HTTP endpoints. A future authenticated adapter calls this
function after verifying controller identity and event authenticity.
"""
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import HotspotSession


def record_authenticated_observation(*, company, router, plan, external_id, source,
                                     started_at, last_seen_at, expires_at=None,
                                     customer=None, voucher=None, username='', mac_address='',
                                     ip_address=None, bytes_download=0, bytes_upload=0,
                                     status=HotspotSession.Status.ACTIVE, ended_at=None):
    if source not in (HotspotSession.Source.RADIUS, HotspotSession.Source.OMADA):
        raise ValidationError('Only trusted RADIUS/Omada adapters may report live observations.')
    if not external_id or len(external_id)>128:
        raise ValidationError('An adapter session identifier is required.')
    if router.company_id != company.pk or plan.company_id != company.pk:
        raise ValidationError('Router and plan must belong to this company.')
    if customer and customer.company_id != company.pk:
        raise ValidationError('Customer must belong to the same company.')
    if voucher and voucher.company_id != company.pk:
        raise ValidationError('Voucher must belong to the same company.')
    if not timezone.is_aware(started_at) or not timezone.is_aware(last_seen_at):
        raise ValidationError('Adapter times must include an offset.')
    if last_seen_at > timezone.now()+timedelta(minutes=2):
        raise ValidationError('Heartbeat timestamp is in the future.')
    if last_seen_at < started_at:
        raise ValidationError('Heartbeat cannot precede session start.')
    if bytes_download < 0 or bytes_upload < 0:
        raise ValidationError('Traffic counters cannot be negative.')
    if status not in HotspotSession.Status.values:
        raise ValidationError('Unknown session status.')

    with transaction.atomic():
        session, created = HotspotSession.objects.select_for_update().get_or_create(
            company=company,router=router,external_id=external_id,
            defaults={'plan':plan,'source':source,'started_at':started_at,'expires_at':expires_at,
                      'last_seen_at':last_seen_at,'status':status,'customer':customer,'voucher':voucher,
                      'username':username,'mac_address':mac_address,'ip_address':ip_address,
                      'bytes_download':bytes_download,'bytes_upload':bytes_upload,'ended_at':ended_at},
        )
        if created: return session
        if session.source != source:
            raise ValidationError('Existing session belongs to another adapter type.')
        # Never allow stale/out-of-order packets to resurrect an ended session.
        if session.last_seen_at and last_seen_at < session.last_seen_at:
            return session
        if session.status != 'ACTIVE' and status == 'ACTIVE':
            return session
        session.last_seen_at=last_seen_at
        session.status=status
        session.ended_at=ended_at if status != 'ACTIVE' else None
        session.expires_at=expires_at or session.expires_at
        session.bytes_download=max(session.bytes_download,bytes_download)
        session.bytes_upload=max(session.bytes_upload,bytes_upload)
        session.ip_address=ip_address or session.ip_address
        session.save(update_fields=['last_seen_at','status','ended_at','expires_at','bytes_download','bytes_upload','ip_address','updated_at'])
        return session
