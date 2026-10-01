from __future__ import annotations

import json
import logging
import re
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.herd.models import Farm

logger = logging.getLogger(__name__)

WMO_CONDITIONS = {
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla con escarcha",
    51: "Llovizna ligera",
    53: "Llovizna moderada",
    55: "Llovizna intensa",
    56: "Llovizna helada ligera",
    57: "Llovizna helada intensa",
    61: "Lluvia ligera",
    63: "Lluvia moderada",
    65: "Lluvia intensa",
    66: "Lluvia helada ligera",
    67: "Lluvia helada intensa",
    71: "Nieve ligera",
    73: "Nieve moderada",
    75: "Nieve intensa",
    77: "Granulos de nieve",
    80: "Chubascos ligeros",
    81: "Chubascos moderados",
    82: "Chubascos intensos",
    85: "Chubascos de nieve ligeros",
    86: "Chubascos de nieve intensos",
    95: "Tormenta electrica",
    96: "Tormenta con granizo",
    97: "Tormenta fuerte",
    99: "Tormenta fuerte con granizo",
}

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REFERENCE = re.compile(r"([A-Z]+)")


class ExternalProviderError(Exception):
    """A recoverable error returned by an external information provider."""


def _cache_key(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"external-info:{prefix}:{sha256(raw.encode()).hexdigest()}"


def _request_bytes(url: str, *, max_bytes: int) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json, application/octet-stream;q=0.9, */*;q=0.8",
            "User-Agent": "KORE-Agro/0.1 external-information",
        },
    )
    try:
        with urlopen(request, timeout=settings.EXTERNAL_INFO_HTTP_TIMEOUT) as response:
            payload = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ExternalProviderError("La fuente externa no respondio a tiempo.") from exc
    if len(payload) > max_bytes:
        raise ExternalProviderError("La fuente externa excedio el tamano permitido.")
    return payload


def _request_json(endpoint: str, params: dict[str, object]) -> dict:
    url = f"{endpoint}?{urlencode(params)}"
    payload = _request_bytes(url, max_bytes=settings.EXTERNAL_INFO_MAX_JSON_BYTES)
    try:
        result = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalProviderError("La fuente externa devolvio datos invalidos.") from exc
    if not isinstance(result, dict) or result.get("error"):
        raise ExternalProviderError("La fuente externa no pudo completar la consulta.")
    return result


def _normalize_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(plain.upper().split())


def _normalize_canton(value: object) -> str:
    return _normalize_text(value).removeprefix("CANTON ").strip()


def _farm_location_candidates(farm: Farm) -> list[str]:
    values = (
        getattr(farm, "weather_location", ""),
        farm.parish,
        farm.canton,
        farm.province,
    )
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _geocode_farm(farm: Farm) -> dict:
    candidates = _farm_location_candidates(farm)
    if not candidates:
        raise ExternalProviderError(
            "Configura la provincia, canton o parroquia de la hacienda para consultar el clima."
        )

    key = _cache_key(
        "geocode",
        getattr(farm, "weather_location", ""),
        farm.province,
        farm.canton,
        farm.parish,
    )
    cached = cache.get(key)
    if cached is not None:
        return cached

    expected_province = _normalize_text(farm.province)
    for candidate in candidates:
        payload = _request_json(
            settings.OPEN_METEO_GEOCODING_URL,
            {
                "name": candidate,
                "count": 10,
                "language": "es",
                "countryCode": "EC",
            },
        )
        results = payload.get("results") or []
        if not results:
            continue
        location = next(
            (
                row
                for row in results
                if not expected_province or _normalize_text(row.get("admin1")) == expected_province
            ),
            results[0],
        )
        resolved = {
            "name": location.get("name") or candidate,
            "province": location.get("admin1") or farm.province,
            "canton": location.get("admin2") or farm.canton,
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "timezone": location.get("timezone") or "America/Guayaquil",
        }
        cache.set(key, resolved, settings.EXTERNAL_INFO_GEOCODE_CACHE_SECONDS)
        return resolved
    raise ExternalProviderError(
        "No se encontro la ubicacion de la hacienda en el servicio meteorologico."
    )


def _number(value: object, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _weather_alerts(days: list[dict]) -> list[dict]:
    upcoming = days[:3]
    alerts = []
    if any((day["rain_probability"] or 0) >= 70 or (day["rain_mm"] or 0) >= 10 for day in upcoming):
        alerts.append(
            {
                "level": "warning",
                "title": "Lluvia probable",
                "detail": (
                    "Revisa accesos, drenajes y labores antes de movilizar personal o ganado."
                ),
            }
        )
    if any((day["wind_max"] or 0) >= 30 for day in upcoming):
        alerts.append(
            {
                "level": "warning",
                "title": "Viento fuerte",
                "detail": "Evita fumigaciones y asegura cubiertas o materiales livianos.",
            }
        )
    if any((day["temperature_max"] or 0) >= 32 for day in upcoming):
        alerts.append(
            {
                "level": "danger",
                "title": "Riesgo de calor",
                "detail": "Prioriza sombra, agua y recorridos del ganado en horas frescas.",
            }
        )
    if any((day["uv_max"] or 0) >= 8 for day in upcoming):
        alerts.append(
            {
                "level": "warning",
                "title": "Radiacion UV alta",
                "detail": "Organiza proteccion y pausas para el personal expuesto.",
            }
        )
    if not alerts:
        alerts.append(
            {
                "level": "normal",
                "title": "Sin alertas operativas",
                "detail": "El pronostico de tres dias no supera los umbrales configurados.",
            }
        )
    return alerts


def get_weather_for_farm(farm: Farm) -> dict:
    location = _geocode_farm(farm)
    key = _cache_key(
        "weather",
        round(float(location["latitude"]), 4),
        round(float(location["longitude"]), 4),
    )
    cached = cache.get(key)
    if cached is not None:
        return cached

    payload = _request_json(
        settings.OPEN_METEO_FORECAST_URL,
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,precipitation_sum,wind_speed_10m_max,"
                "et0_fao_evapotranspiration,uv_index_max"
            ),
            "timezone": location["timezone"],
            "forecast_days": 7,
        },
    )
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    days = []
    for index, raw_date in enumerate(daily.get("time") or []):

        def at(name: str, position: int = index):
            values = daily.get(name) or []
            return values[position] if position < len(values) else None

        code = at("weather_code")
        days.append(
            {
                "date": date.fromisoformat(raw_date),
                "condition": WMO_CONDITIONS.get(code, "Condiciones variables"),
                "temperature_max": _number(at("temperature_2m_max")),
                "temperature_min": _number(at("temperature_2m_min")),
                "rain_probability": _number(at("precipitation_probability_max"), 0),
                "rain_mm": _number(at("precipitation_sum")),
                "wind_max": _number(at("wind_speed_10m_max")),
                "evapotranspiration": _number(at("et0_fao_evapotranspiration"), 2),
                "uv_max": _number(at("uv_index_max")),
            }
        )

    if not days:
        raise ExternalProviderError("El servicio meteorologico no devolvio un pronostico util.")
    result = {
        "location": location,
        "current": {
            "observed_at": current.get("time"),
            "condition": WMO_CONDITIONS.get(
                current.get("weather_code"), "Condiciones variables"
            ),
            "temperature": _number(current.get("temperature_2m")),
            "humidity": _number(current.get("relative_humidity_2m"), 0),
            "precipitation": _number(current.get("precipitation"), 2),
            "wind": _number(current.get("wind_speed_10m")),
        },
        "days": days,
        "alerts": _weather_alerts(days),
        "fetched_at": timezone.now(),
        "source_url": "https://open-meteo.com/en/docs",
    }
    result["week"] = {
        "rain_total": round(sum(day["rain_mm"] or 0 for day in days), 1),
        "wind_max": max((day["wind_max"] or 0 for day in days), default=0),
        "evapotranspiration_total": round(
            sum(day["evapotranspiration"] or 0 for day in days), 2
        ),
        "uv_max": max((day["uv_max"] or 0 for day in days), default=0),
    }
    result["chart"] = {
        "dates": [day["date"].isoformat() for day in days],
        "conditions": [day["condition"] for day in days],
        "temperature_max": [day["temperature_max"] for day in days],
        "temperature_min": [day["temperature_min"] for day in days],
        "rain_probability": [day["rain_probability"] for day in days],
        "rain_mm": [day["rain_mm"] for day in days],
        "wind_max": [day["wind_max"] for day in days],
        "evapotranspiration": [day["evapotranspiration"] for day in days],
        "uv_max": [day["uv_max"] for day in days],
    }
    cache.set(key, result, settings.EXTERNAL_INFO_WEATHER_CACHE_SECONDS)
    return result


def _column_index(reference: str) -> int:
    match = _CELL_REFERENCE.match(reference)
    if not match:
        return 0
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _worksheet_rows(root: ElementTree.Element, shared_strings: list[str]) -> list[list[str]]:
    namespace = {"m": _MAIN_NS}
    rows = []
    for row in root.findall(".//m:sheetData/m:row", namespace):
        values = {}
        for cell in row.findall("m:c", namespace):
            index = _column_index(cell.attrib.get("r", "A1"))
            cell_type = cell.attrib.get("t")
            value_node = cell.find("m:v", namespace)
            value = value_node.text if value_node is not None else ""
            if cell_type == "s" and value:
                value = shared_strings[int(value)]
            elif cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//m:t", namespace))
            values[index] = value
        if values:
            rows.append([values.get(index, "") for index in range(max(values) + 1)])
    return rows


def _xlsx_sheets(payload: bytes) -> dict[str, list[list[str]]]:
    try:
        with zipfile.ZipFile(BytesIO(payload)) as workbook:
            uncompressed_size = sum(item.file_size for item in workbook.infolist())
            if uncompressed_size > settings.EXTERNAL_INFO_MAX_XLSX_BYTES:
                raise ExternalProviderError("El archivo sanitario descomprimido excede el limite.")
            namespace = {"m": _MAIN_NS, "r": _OFFICE_REL_NS}
            shared_strings = []
            if "xl/sharedStrings.xml" in workbook.namelist():
                shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
                shared_strings = [
                    "".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t"))
                    for item in shared_root.findall("m:si", namespace)
                ]
            workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
            relationships_root = ElementTree.fromstring(
                workbook.read("xl/_rels/workbook.xml.rels")
            )
            targets = {
                relation.attrib["Id"]: relation.attrib["Target"]
                for relation in relationships_root.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
            }
            sheets = {}
            for sheet in workbook_root.findall("m:sheets/m:sheet", namespace):
                relationship_id = sheet.attrib[f"{{{_OFFICE_REL_NS}}}id"]
                target = targets[relationship_id].lstrip("/")
                sheet_path = target if target.startswith("xl/") else f"xl/{target}"
                sheet_root = ElementTree.fromstring(workbook.read(sheet_path))
                sheets[sheet.attrib["name"]] = _worksheet_rows(sheet_root, shared_strings)
            return sheets
    except ExternalProviderError:
        raise
    except (IndexError, KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ExternalProviderError("El archivo sanitario no tiene un formato compatible.") from exc


def _parse_int(value: object) -> int:
    try:
        return int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _summarize_vaccination_file(payload: bytes) -> dict:
    totals = {
        "aftosa": {"province": {}, "canton": {}, "year": 0},
        "rabia": {"province": {}, "canton": {}, "year": 0},
    }
    for sheet_name, rows in _xlsx_sheets(payload).items():
        if not rows:
            continue
        category = "rabia" if "RABIA" in _normalize_text(sheet_name) else "aftosa"
        headers = [_normalize_text(value) for value in rows[0]]
        try:
            province_index = headers.index("PROVINCIA")
            canton_index = headers.index("CANTON")
            dose_index = next(index for index, value in enumerate(headers) if "DOSIS" in value)
        except (ValueError, StopIteration):
            continue
        year_index = next((index for index, value in enumerate(headers) if value == "ANO"), None)
        for row in rows[1:]:
            province = _normalize_text(row[province_index] if province_index < len(row) else "")
            canton = _normalize_canton(row[canton_index] if canton_index < len(row) else "")
            doses = _parse_int(row[dose_index] if dose_index < len(row) else 0)
            if not province or not canton:
                continue
            totals[category]["province"][province] = (
                totals[category]["province"].get(province, 0) + doses
            )
            location_key = f"{province}|{canton}"
            totals[category]["canton"][location_key] = (
                totals[category]["canton"].get(location_key, 0) + doses
            )
            if year_index is not None and year_index < len(row):
                totals[category]["year"] = max(
                    totals[category]["year"], _parse_int(row[year_index])
                )
    return totals


def _latest_vaccination_resource() -> tuple[dict, dict]:
    package = _request_json(
        settings.AGROCALIDAD_CKAN_PACKAGE_URL,
        {"id": settings.AGROCALIDAD_VACCINATION_DATASET_ID},
    ).get("result") or {}
    resources = []
    for resource in package.get("resources") or []:
        description = _normalize_text(resource.get("description"))
        name_tokens = f" {_normalize_text(resource.get('name')).replace('_', ' ')} "
        is_data_file = "CONJUNTO DE DATOS" in description or " CD " in name_tokens
        if is_data_file and resource.get("url"):
            resources.append(resource)
    if not resources:
        raise ExternalProviderError("Agrocalidad no publico un corte sanitario procesable.")
    resource = max(resources, key=lambda row: row.get("last_modified") or row.get("created") or "")
    return package, resource


def _resource_totals(resource: dict) -> dict:
    key = _cache_key("vaccination-resource", resource.get("id"), resource.get("last_modified"))
    cached = cache.get(key)
    if cached is not None:
        return cached
    declared_size = _parse_int(resource.get("size"))
    if declared_size and declared_size > settings.EXTERNAL_INFO_MAX_DOWNLOAD_BYTES:
        raise ExternalProviderError("El corte sanitario excede el limite de descarga configurado.")
    payload = _request_bytes(resource["url"], max_bytes=settings.EXTERNAL_INFO_MAX_DOWNLOAD_BYTES)
    totals = _summarize_vaccination_file(payload)
    cache.set(key, totals, settings.EXTERNAL_INFO_SANITARY_CACHE_SECONDS)
    return totals


def _parse_external_date(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def get_vaccination_summary(farm: Farm) -> dict:
    province = _normalize_text(farm.province)
    canton = _normalize_canton(farm.canton)
    if not province:
        raise ExternalProviderError(
            "Configura la provincia de la hacienda para consultar los datos sanitarios."
        )

    package, resource = _latest_vaccination_resource()
    totals = _resource_totals(resource)
    location_key = f"{province}|{canton}"

    def category_summary(category: str) -> dict:
        data = totals[category]
        return {
            "year": data["year"] or None,
            "canton_doses": data["canton"].get(location_key) if canton else None,
            "province_doses": data["province"].get(province),
        }

    return {
        "dataset_title": package.get("title") or "Datos de vacunacion",
        "resource_name": resource.get("name") or "Ultimo corte publicado",
        "published_at": _parse_external_date(resource.get("last_modified")),
        "province": farm.province,
        "canton": farm.canton,
        "aftosa": category_summary("aftosa"),
        "rabia": category_summary("rabia"),
        "source_url": (
            "https://www.datosabiertos.gob.ec/dataset/"
            f"{settings.AGROCALIDAD_VACCINATION_DATASET_ID}"
        ),
        "download_url": resource["url"],
    }


def get_external_information(farm: Farm) -> dict:
    providers = {"weather": get_weather_for_farm, "vaccination": get_vaccination_summary}
    result = {}
    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {executor.submit(provider, farm): name for name, provider in providers.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result[name] = future.result()
                result[f"{name}_error"] = ""
            except ExternalProviderError as exc:
                result[name] = None
                result[f"{name}_error"] = str(exc)
            except Exception:
                logger.exception("Unexpected %s external information error", name)
                result[name] = None
                result[f"{name}_error"] = "No fue posible actualizar esta consulta en este momento."
    return result
