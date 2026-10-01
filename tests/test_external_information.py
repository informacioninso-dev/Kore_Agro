from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from django.core.cache import cache
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.dashboard.external_info import (
    ExternalProviderError,
    _latest_vaccination_resource,
    _summarize_vaccination_file,
    get_external_information,
    get_weather_for_farm,
)
from apps.herd.models import Farm
from tests.factories import authenticated_manager_client, create_tenant


def _worksheet_xml(rows: list[list[str]]) -> str:
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            column = chr(ord("A") + column_index)
            cells.append(
                f'<c r="{column}{row_index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


def _vaccination_workbook() -> bytes:
    workbook = BytesIO()
    with ZipFile(workbook, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Fiebre aftosa" sheetId="1" r:id="rId1"/>'
            '<sheet name="Rabia" sheetId="2" r:id="rId2"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            _worksheet_xml(
                [
                    ["PROVINCIA", "CANTON", "TOTAL DOSIS AFTOSA", "ANO"],
                    ["PICHINCHA", "QUITO", "120", "2026"],
                    ["PICHINCHA", "MEJIA", "80", "2026"],
                ]
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            _worksheet_xml(
                [
                    ["PROVINCIA", "CANTON", "DOSIS APLICADAS", "ANO"],
                    ["PICHINCHA", "QUITO", "15", "2026"],
                ]
            ),
        )
    return workbook.getvalue()


def test_weather_adapter_geocodes_farm_and_builds_operational_alerts():
    cache.clear()
    farm = SimpleNamespace(
        province="Pichincha",
        canton="Quito",
        parish="",
        weather_location="Tumbaco",
    )
    geocoding = {
        "results": [
            {
                "name": "Tumbaco",
                "admin1": "Pichincha",
                "admin2": "Canton Quito",
                "latitude": -0.21477,
                "longitude": -78.40067,
                "timezone": "America/Guayaquil",
            }
        ]
    }
    forecast = {
        "current": {
            "time": "2026-10-01T09:00",
            "temperature_2m": 19.4,
            "relative_humidity_2m": 66,
            "precipitation": 0,
            "weather_code": 3,
            "wind_speed_10m": 3.3,
        },
        "daily": {
            "time": ["2026-10-01", "2026-10-02"],
            "weather_code": [80, 63],
            "temperature_2m_max": [22.8, 19.5],
            "temperature_2m_min": [13.3, 14.5],
            "precipitation_probability_max": [100, 98],
            "precipitation_sum": [6.8, 17.4],
            "wind_speed_10m_max": [11.8, 6.2],
            "et0_fao_evapotranspiration": [3.73, 2.14],
            "uv_index_max": [7.2, 5.5],
        },
    }

    with patch(
        "apps.dashboard.external_info._request_json", side_effect=[geocoding, forecast]
    ) as request_json:
        result = get_weather_for_farm(farm)

    assert request_json.call_args_list[0].args[1]["name"] == "Tumbaco"
    assert result["location"]["name"] == "Tumbaco"
    assert result["current"]["condition"] == "Nublado"
    assert result["days"][1]["rain_mm"] == 17.4
    assert result["alerts"][0]["title"] == "Lluvia probable"
    assert result["week"]["rain_total"] == 24.2
    assert result["chart"]["temperature_max"] == [22.8, 19.5]


def test_vaccination_workbook_is_aggregated_by_province_and_canton():
    totals = _summarize_vaccination_file(_vaccination_workbook())

    assert totals["aftosa"]["province"]["PICHINCHA"] == 200
    assert totals["aftosa"]["canton"]["PICHINCHA|QUITO"] == 120
    assert totals["rabia"]["canton"]["PICHINCHA|QUITO"] == 15
    assert totals["rabia"]["year"] == 2026


def test_latest_vaccination_resource_recognizes_ckan_cd_filename():
    package = {
        "result": {
            "title": "Datos de vacunacion",
            "resources": [
                {
                    "id": "data",
                    "name": "AGROCALIDAD_AFTOSA_CD_2025_DIC.xls",
                    "description": "Informacion de vacunacion del ultimo trimestre.",
                    "last_modified": "2025-12-29T16:30:22",
                    "url": "https://example.test/data.xls",
                },
                {
                    "id": "dictionary",
                    "name": "AGROCALIDAD_AFTOSA_DD_2025_DIC.xls",
                    "description": "Informacion de vacunacion del ultimo trimestre.",
                    "last_modified": "2025-12-29T16:32:15",
                    "url": "https://example.test/dictionary.xls",
                },
            ],
        }
    }

    with patch("apps.dashboard.external_info._request_json", return_value=package):
        _, resource = _latest_vaccination_resource()

    assert resource["id"] == "data"


def test_external_information_keeps_working_when_providers_fail():
    farm = SimpleNamespace(province="Pichincha", canton="Quito", parish="Tumbaco")
    with (
        patch(
            "apps.dashboard.external_info.get_weather_for_farm",
            side_effect=ExternalProviderError("Clima no disponible."),
        ),
        patch(
            "apps.dashboard.external_info.get_vaccination_summary",
            side_effect=ExternalProviderError("Datos sanitarios no disponibles."),
        ),
    ):
        result = get_external_information(farm)

    assert result["weather"] is None
    assert result["weather_error"] == "Clima no disponible."
    assert result["vaccination"] is None
    assert result["vaccination_error"] == "Datos sanitarios no disponibles."


@pytest.mark.django_db(transaction=True)
def test_information_center_renders_integrated_data_for_selected_farm():
    tenant = create_tenant("externalinfo")
    with tenant_context(tenant):
        farm = Farm.objects.create(
            name="Hacienda Norte",
            code="NORTE",
            province="Pichincha",
            canton="Quito",
            parish="Tumbaco",
        )
    client = authenticated_manager_client(tenant)
    snapshot = {
        "weather": {
            "location": {"name": "Tumbaco", "province": "Pichincha"},
            "current": {
                "temperature": 19.4,
                "humidity": 66,
                "precipitation": 0,
                "wind": 3.3,
                "condition": "Nublado",
            },
            "days": [
                {
                    "date": date(2026, 10, 1),
                    "condition": "Chubascos ligeros",
                    "temperature_min": 13.3,
                    "temperature_max": 22.8,
                    "rain_probability": 100,
                    "rain_mm": 6.8,
                    "wind_max": 11.8,
                    "evapotranspiration": 3.73,
                }
            ],
            "alerts": [
                {"level": "warning", "title": "Lluvia probable", "detail": "Revisa accesos."}
            ],
            "week": {
                "rain_total": 6.8,
                "wind_max": 11.8,
                "evapotranspiration_total": 3.73,
                "uv_max": 7.2,
            },
            "chart": {
                "dates": ["2026-10-01"],
                "conditions": ["Chubascos ligeros"],
                "temperature_max": [22.8],
                "temperature_min": [13.3],
                "rain_probability": [100],
                "rain_mm": [6.8],
                "wind_max": [11.8],
                "evapotranspiration": [3.73],
                "uv_max": [7.2],
            },
            "fetched_at": timezone.now(),
            "source_url": "https://open-meteo.com/en/docs",
        },
        "weather_error": "",
        "vaccination": {
            "dataset_title": "Datos de vacunacion",
            "resource_name": "Corte 2026",
            "published_at": timezone.now(),
            "province": "Pichincha",
            "canton": "Quito",
            "aftosa": {"year": 2026, "canton_doses": 120, "province_doses": 200},
            "rabia": {"year": 2026, "canton_doses": 15, "province_doses": 15},
            "source_url": "https://www.datosabiertos.gob.ec/",
            "download_url": "https://www.datosabiertos.gob.ec/corte.xls",
        },
        "vaccination_error": "",
    }

    with patch("apps.dashboard.views.get_external_information", return_value=snapshot):
        response = client.get(f"/informacion/?farm={farm.id}")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Informacion para decidir" in html
    assert "Tumbaco, Pichincha" in html
    assert "Lluvia probable" in html
    assert "weatherChart" in html
    assert "Actualizar consulta" not in html
    assert "Vacunacion publicada" in html
    assert "Datos de vacunacion" in html
