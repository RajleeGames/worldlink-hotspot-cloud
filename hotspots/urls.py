from django.urls import path
from . import views
urlpatterns = [
    path('sessions/', views.sessions, name='sessions'),
    path('sessions/export/', views.sessions_export, name='sessions_export'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('customers/', views.customers, name='customers'),
    path('customers/new/', views.customer_edit, name='customer_new'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
]
