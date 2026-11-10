from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include, reverse_lazy
from cloud.views import LoginPage, SignupPage, language_change

admin.site.site_header = 'WorldLink Hotspot Cloud | Administration'
admin.site.site_title = 'WorldLink Cloud Admin'
admin.site.index_title = 'Platform administration'
# Technical fallback only: WorldLink staff use the HTML console.
admin.site.has_permission = lambda request: bool(request.user.is_authenticated and request.user.is_active and request.user.is_superuser)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', LoginPage.as_view(), name='login'),
    path('register/', SignupPage.as_view(), name='register'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('language/', language_change, name='language_change'),
    path('', include(('cloud.urls', 'cloud'), namespace='cloud')),
    path('business/', include(('tenants.urls', 'tenants'), namespace='tenants')),
    path('network/', include(('networks.urls', 'networks'), namespace='networks')),
    path('vouchers/', include(('vouchers.urls', 'vouchers'), namespace='vouchers')),
    path('hotspots/', include(('hotspots.urls', 'hotspots'), namespace='hotspots')),
    path('console/', include(('controlcenter.urls', 'controlcenter'), namespace='controlcenter')),
    path('', include(('portal.urls', 'portal'), namespace='portal')),
    path('payments/', include(('payments.urls', 'payments'), namespace='payments')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
