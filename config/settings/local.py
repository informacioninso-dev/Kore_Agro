from .base import *  # noqa: F403

DEBUG = True

# Development serves source static files directly; production keeps WhiteNoise's manifest storage.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

