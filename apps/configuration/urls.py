from django.urls import path

from . import views

app_name = "platform"

urlpatterns = [
    path("login/", views.platform_login, name="login"),
    path("logout/", views.platform_logout, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("organizaciones/", views.organization_list, name="organization_list"),
    path("organizaciones/nueva/", views.organization_create, name="organization_create"),
    path(
        "organizaciones/<int:pk>/",
        views.organization_edit,
        name="organization_edit",
    ),
    path("catalogo/", views.catalog, name="catalog"),
    path("catalogo/perfiles/nuevo/", views.profile_create, name="profile_create"),
    path("catalogo/perfiles/<int:pk>/", views.profile_edit, name="profile_edit"),
    path(
        "catalogo/capacidades/nueva/",
        views.capability_create,
        name="capability_create",
    ),
    path(
        "catalogo/capacidades/<int:pk>/",
        views.capability_edit,
        name="capability_edit",
    ),
]
