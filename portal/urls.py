from django.urls import path
from . import views
urlpatterns = [
    path('guest/settings/', views.settings, name='settings'),
    path('wifi/<slug:slug>/', views.public, name='public'),
    path('wifi/<slug:slug>/voucher/', views.voucher_redeem, name='voucher_redeem'),
    path('wifi/<slug:slug>/voucher/<uuid:public_id>/', views.voucher_status, name='voucher_status'),
    path('wifi/<slug:slug>/checkout/<int:plan_id>/', views.checkout, name='checkout'),
    path('wifi/<slug:slug>/pay/<int:plan_id>/', views.evpay_checkout, name='evpay_checkout'),
    path('wifi/<slug:slug>/payment/<uuid:public_id>/', views.evpay_status, name='evpay_status'),
    path('wifi/<slug:slug>/status/<uuid:public_id>/', views.order_status, name='status'),
]
