from django.urls import path
from . import views
urlpatterns = [
    path('guest/settings/', views.settings, name='settings'),
    path('wifi/<slug:slug>/', views.public, name='public'),
    path('wifi/<slug:slug>/checkout/<int:plan_id>/', views.checkout, name='checkout'),
    path('wifi/<slug:slug>/status/<uuid:public_id>/', views.order_status, name='status'),
]
