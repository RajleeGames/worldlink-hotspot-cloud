from django.contrib import admin
from .models import HotspotCustomer, HotspotSession

@admin.register(HotspotCustomer)
class HotspotCustomerAdmin(admin.ModelAdmin):
    list_display=('full_name','company','phone','email','created_at')
    search_fields=('full_name','phone','email','company__name')
    list_filter=('company',)

@admin.register(HotspotSession)
class HotspotSessionAdmin(admin.ModelAdmin):
    list_display=('username','company','router','plan','source','status','started_at','expires_at','last_seen_at')
    list_filter=('company','source','status')
    search_fields=('username','mac_address','external_id','customer__full_name')
    readonly_fields=('external_id','source','last_seen_at','bytes_download','bytes_upload')
