from django.contrib import admin
from .models import PlatformAudit

@admin.register(PlatformAudit)
class PlatformAuditAdmin(admin.ModelAdmin):
    list_display=('created_at','actor','company','action','note')
    search_fields=('actor__username','company__name','action','note')
    list_filter=('action',)
    readonly_fields=('actor','company','action','note','created_at')
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
