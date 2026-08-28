from django.urls import path

from . import views

app_name = "field"

urlpatterns = [
    path("", views.field_app, name="app"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("manifest.webmanifest", views.webmanifest, name="manifest"),
]

