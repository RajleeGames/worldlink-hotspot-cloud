from django.urls import path
from . import views
urlpatterns = [
    path('',views.batch_list,name='batches'),
    path('create/',views.batch_create,name='create'),
    path('batch/<int:pk>/',views.batch_detail,name='batch_detail'),
    path('batch/<int:pk>/edit/',views.batch_edit,name='batch_edit'),
    path('batch/<int:pk>/delete/',views.batch_delete,name='batch_delete'),
    path('batch/<int:pk>/export/',views.batch_export,name='export'),
    path('sell/<int:pk>/',views.manual_sell,name='sell'),
]
