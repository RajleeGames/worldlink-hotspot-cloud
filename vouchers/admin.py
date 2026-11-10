from django.contrib import admin
from .models import VoucherBatch,Voucher,ManualSale

@admin.register(VoucherBatch)
class VoucherBatchAdmin(admin.ModelAdmin):
    list_display=('id','company','plan','quantity','created_at')
    list_filter=('company',)

@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display=('code','company','batch','status','created_at')
    list_filter=('company','status')
    search_fields=('code',)

@admin.register(ManualSale)
class ManualSaleAdmin(admin.ModelAdmin):
    list_display=('voucher','company','amount','method','created_at')
    list_filter=('company','method')
