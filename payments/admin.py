from django.contrib import admin
from .models import PaymentMethod, PaymentOrder, PaymentAudit
@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display=('company','channel','label','is_active')
    search_fields=('company__name','label')
@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display=('reference','company','status','amount','created_at')
    search_fields=('reference','customer_name','customer_phone')
    readonly_fields=('reference', 'public_id', 'verified_by', 'verified_at')
@admin.register(PaymentAudit)
class PaymentAuditAdmin(admin.ModelAdmin):
    list_display=('order','actor','action','created_at')
