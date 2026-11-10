import secrets
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import PaymentOrder, PaymentAudit


def create_pending_order(*, company, plan, method, name, phone):
    if plan.company_id != company.pk or method.company_id != company.pk or not plan.is_active or not method.is_active:
        raise ValueError('Invalid cross-business payment request.')
    for attempt in range(5):
        try:
            with transaction.atomic():
                reference = 'WHC-' + secrets.token_hex(5).upper()
                order = PaymentOrder.objects.create(
                    company=company, plan=plan, method=method, amount=plan.price,
                    reference=reference, customer_name=name, customer_phone=phone,
                )
                PaymentAudit.objects.create(order=order, action='CREATED', comment='Pending; no payment received or router access granted.')
                return order
        except IntegrityError:
            if attempt == 4:
                raise
    raise RuntimeError('Could not create an order')


def update_order_status(*, order, actor, status, merchant_reference='', note=''):
    if status not in (PaymentOrder.Status.PAID, PaymentOrder.Status.CANCELLED):
        raise ValueError('Unsupported order action.')
    with transaction.atomic():
        updated = PaymentOrder.objects.filter(pk=order.pk, status=PaymentOrder.Status.PENDING).update(
            status=status,
            verified_by=actor if status == PaymentOrder.Status.PAID else None,
            verified_at=timezone.now() if status == PaymentOrder.Status.PAID else None,
            merchant_reference=merchant_reference.strip() if status == PaymentOrder.Status.PAID else '',
            review_note=note[:250],
        )
        if updated:
            PaymentAudit.objects.create(order_id=order.pk, actor=actor, action=status, comment=note[:250])
        return bool(updated)
