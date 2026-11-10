from django.urls import path
from . import views, evpay_views
urlpatterns = [
    path('', views.orders, name='orders'),
    path('evpay/', evpay_views.lab, name='evpay_lab'),
    path('evpay/auth/', evpay_views.test_auth, name='evpay_auth'),
    path('evpay/start/', evpay_views.create_test, name='evpay_start'),
    path('evpay/reconcile/<int:pk>/', evpay_views.reconcile_test, name='evpay_reconcile'),
    path('evpay/webhook/<slug:token>/', evpay_views.webhook, name='evpay_webhook'),
    path('order/<int:pk>/', views.order_detail, name='order_detail'),
    path('order/<int:pk>/verify/', views.verify_order, name='verify'),
    path('order/<int:pk>/cancel/', views.cancel_order, name='cancel'),
    path('methods/', views.methods, name='methods'),
    path('methods/new/', views.method_create, name='method_create'),
    path('methods/<int:pk>/edit/', views.method_edit, name='method_edit'),
    path('methods/<int:pk>/disable/', views.method_disable, name='method_disable'),
]
