from django.urls import path
from . import views
urlpatterns = [
    path('switch/', views.switch_company, name='switch'),
    path('settings/', views.settings, name='settings'),
    path('no-access/', views.no_company, name='no_company'),
]
