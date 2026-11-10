from django.urls import path
from . import views
urlpatterns=[
    path('',views.home,name='home'),
    path('dashboard/',views.dashboard,name='dashboard'),
    path('reports/',views.reports,name='reports'),
    path('expenses/',views.expenses,name='expenses'),
    path('expenses/new/',views.expense_edit,name='expense_new'),
    path('expenses/<int:pk>/edit/',views.expense_edit,name='expense_edit'),
    path('expenses/<int:pk>/delete/',views.expense_delete,name='expense_delete'),
    path('profile/',views.profile,name='profile'),
]
