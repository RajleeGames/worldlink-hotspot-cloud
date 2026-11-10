from django.contrib import admin
from .models import CaptivePortal
@admin.register(CaptivePortal)
class CaptivePortalAdmin(admin.ModelAdmin):
    list_display = ('company', 'enabled', 'updated_at')
    search_fields = ('company__name',)
