from django.contrib import admin
from .models import PlatformBranding, Expense


@admin.register(PlatformBranding)
class PlatformBrandingAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'name', 'has_logo')
    fields = ('name', 'product_name', 'tagline', 'logo')

    @admin.display(boolean=True, description='Logo uploaded')
    def has_logo(self, obj):
        return bool(obj.logo)

    def has_add_permission(self, request):
        # Keep a single platform-wide record.
        return super().has_add_permission(request) and not PlatformBranding.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date','company','category','description','amount','recorded_by')
    list_filter = ('company','category','date')
    search_fields = ('description','company__name')
