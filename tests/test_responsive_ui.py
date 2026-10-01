from pathlib import Path

import pytest
from django.contrib.staticfiles import finders

from tests.factories import authenticated_manager_client, create_tenant

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _static_text(relative_path: str) -> str:
    resolved = finders.find(relative_path)
    assert resolved is not None
    return Path(resolved).read_text(encoding="utf-8")


def _template_text(relative_path: str) -> str:
    return (PROJECT_ROOT / "templates" / relative_path).read_text(encoding="utf-8")


def test_tenant_shell_has_tablet_mobile_and_secondary_navigation():
    stylesheet = _static_text("ui/css/shell.css")
    template = _template_text("base.html")

    assert "@media (min-width: 901px) and (max-width: 1180px)" in stylesheet
    assert "@media (max-width: 900px)" in stylesheet
    assert "env(safe-area-inset-bottom)" in stylesheet
    assert 'class="kore-mobile-more"' in template
    assert "dashboard:tenant_settings" in template
    assert "identity:logout" in template
    assert template.count("'/cumplimiento/' in request.path") == 2


def test_platform_core_tables_have_mobile_card_labels():
    stylesheet = _static_text("platform/css/app.css")
    dashboard = _template_text("platform/dashboard.html")
    organizations = _template_text("platform/organization_list.html")
    catalog = _template_text("platform/catalog.html")

    assert "@media (max-width: 640px)" in stylesheet
    assert "content: attr(data-label)" in stylesheet
    assert 'class="platform-responsive-table"' in dashboard
    assert 'data-label="Organizacion"' in dashboard
    assert 'class="platform-responsive-table"' in organizations
    assert 'data-label="Accion"' in organizations
    assert catalog.count('class="platform-responsive-table"') == 2
    assert 'data-label="Capacidad"' in catalog


def test_field_ui_has_touch_and_landscape_adaptations():
    stylesheet = _static_text("field/css/app.css")
    service_worker = _static_text("field/sw.js")

    assert "min-height: 3rem" in stylesheet
    assert "env(safe-area-inset-top)" in stylesheet
    assert "@media (orientation: landscape) and (max-height: 600px)" in stylesheet
    assert 'const CACHE_NAME = "kore-agro-field-v13"' in service_worker


@pytest.mark.django_db(transaction=True)
def test_documents_navigation_is_active_on_compliance_screen():
    tenant = create_tenant("documentsactive")
    client = authenticated_manager_client(tenant)

    response = client.get("/cumplimiento/")
    html = response.content.decode()

    assert response.status_code == 200
    assert html.count('class="is-active" href="/cumplimiento/"') == 2
