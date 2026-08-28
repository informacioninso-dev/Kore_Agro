from django.conf import settings
from django.http import FileResponse
from django.shortcuts import render
from django.templatetags.static import static


def field_app(request):
    return render(
        request,
        "field/app.html",
        {
            "service_worker_url": "/field/sw.js",
            "manifest_url": "/field/manifest.webmanifest",
            "app_js_url": static("field/js/app.js"),
            "app_css_url": static("field/css/app.css"),
        },
    )


def service_worker(request):
    sw_path = settings.BASE_DIR / "static" / "field" / "sw.js"
    return FileResponse(sw_path.open("rb"), content_type="application/javascript")


def webmanifest(request):
    manifest_path = settings.BASE_DIR / "static" / "field" / "manifest.webmanifest"
    return FileResponse(manifest_path.open("rb"), content_type="application/manifest+json")
