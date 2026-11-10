from django.urls import path
from . import views
urlpatterns = [
    path('routers/',views.router_list,name='routers'),
    path('routers/new/',views.router_edit,name='router_new'),
    path('routers/<int:pk>/edit/',views.router_edit,name='router_edit'),
    path('routers/<int:pk>/delete/',views.router_delete,name='router_delete'),
    path('locations/',views.location_list,name='locations'),
    path('locations/new/',views.location_add,name='location_new'),
    path('locations/<int:pk>/edit/',views.location_add,name='location_edit'),
    path('locations/<int:pk>/delete/',views.location_delete,name='location_delete'),
    path('plans/',views.plan_list,name='plans'),
    path('plans/new/',views.plan_edit,name='plan_new'),
    path('plans/<int:pk>/edit/',views.plan_edit,name='plan_edit'),
    path('plans/<int:pk>/delete/',views.plan_delete,name='plan_delete'),
]
