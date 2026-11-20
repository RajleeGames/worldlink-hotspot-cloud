from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('numbers/new/', views.destination_add, name='destination_add'),
    path('withdraw/new/', views.withdrawal_new, name='withdrawal_new'),
    path('withdraw/<int:pk>/cancel/', views.withdrawal_cancel, name='withdrawal_cancel'),
    path('worldlink/', views.queue, name='queue'),
    path('worldlink/numbers/<int:pk>/review/', views.destination_review, name='destination_review'),
    path('worldlink/withdrawals/<int:pk>/', views.withdrawal_detail, name='withdrawal_detail'),
    path('worldlink/withdrawals/<int:pk>/claim/', views.withdrawal_claim, name='withdrawal_claim'),
    path('worldlink/withdrawals/<int:pk>/review/', views.withdrawal_review, name='withdrawal_review'),
    path('worldlink/collections/new/', views.collection_new, name='collection_new'),
    path('worldlink/evpay/<int:pk>/clearance/', views.evpay_clearance, name='evpay_clearance'),
]
