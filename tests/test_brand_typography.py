from pathlib import Path

from django.contrib.staticfiles import finders

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_PATHS = (
    "ui/fonts/AtkinsonHyperlegible-Regular.woff2",
    "ui/fonts/AtkinsonHyperlegible-Bold.woff2",
)
SURFACE_TEMPLATES = (
    "templates/base.html",
    "templates/identity/login.html",
    "templates/platform/base.html",
    "templates/platform/login.html",
    "templates/field/app.html",
)


def _static_path(relative_path: str) -> Path:
    resolved = finders.find(relative_path)
    assert resolved is not None
    return Path(resolved)


def test_brand_fonts_are_local_valid_woff2_files():
    stylesheet = _static_path("ui/css/typography.css").read_text(encoding="utf-8")

    assert stylesheet.count("@font-face") == 2
    assert 'font-family: "Atkinson Hyperlegible"' in stylesheet
    assert "http://" not in stylesheet
    assert "https://" not in stylesheet
    for font_path in FONT_PATHS:
        assert _static_path(font_path).read_bytes()[:4] == b"wOF2"


def test_all_application_surfaces_load_brand_typography():
    for template_path in SURFACE_TEMPLATES:
        template = (PROJECT_ROOT / template_path).read_text(encoding="utf-8")
        assert "ui/css/typography.css" in template


def test_login_uses_versioned_brand_styles_without_legacy_fonts():
    template = (PROJECT_ROOT / "templates/identity/login.html").read_text(encoding="utf-8")
    stylesheet = _static_path("identity/css/login.css").read_text(encoding="utf-8")

    assert "identity/css/login.css' %}?v=20261001-brand1" in template
    assert "Georgia" not in stylesheet
    assert "Trebuchet" not in stylesheet
    assert "var(--kore-font-family)" in stylesheet


def test_field_pwa_caches_brand_typography_for_offline_use():
    service_worker = _static_path("field/sw.js").read_text(encoding="utf-8")

    assert 'const CACHE_NAME = "kore-agro-field-v13"' in service_worker
    assert '"/static/ui/css/typography.css"' in service_worker
    for font_path in FONT_PATHS:
        assert f'"/static/{font_path}"' in service_worker
