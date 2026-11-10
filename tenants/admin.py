from django.contrib import admin
from .models import Company, Membership

class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ('user',)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'city', 'subscription_ends', 'created_at')
    readonly_fields = ('slug',)
    fields = ('name','slug','logo','email','phone','city','status','subscription_ends')
    search_fields = ('name', 'slug', 'email')
    list_filter = ('status',)
    inlines = (MembershipInline,)

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role')
    search_fields = ('user__username', 'company__name')
    list_filter = ('role',)
    autocomplete_fields = ('company', 'user')
