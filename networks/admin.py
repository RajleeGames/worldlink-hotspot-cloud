from django.contrib import admin
from .models import Location, Router, WifiPlan
for model in (Location,Router,WifiPlan):
    admin.site.register(model)
