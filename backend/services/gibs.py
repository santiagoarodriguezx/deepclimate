"""Small cached NASA GIBS WMTS catalog lookup used by the satellite explorer."""

import datetime
import threading
import time
import xml.etree.ElementTree as ET

import httpx

CAPABILITIES_URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"
LAYERS = (
    "MODIS_Terra_CorrectedReflectance_TrueColor",
    "IMERG_Precipitation_Rate_30min",
)
_cache: dict | None = None
_cache_until = 0.0
_cache_lock = threading.Lock()


def get_gibs_layers(force_refresh: bool = False) -> dict:
    global _cache, _cache_until
    now = time.monotonic()
    if _cache is not None and _cache_until > now and not force_refresh:
        return _cache
    with _cache_lock:
        now = time.monotonic()
        if _cache is not None and _cache_until > now and not force_refresh:
            return _cache
        response = httpx.get(CAPABILITIES_URL, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespaces = {
            "wmts": "http://www.opengis.net/wmts/1.0",
            "ows": "http://www.opengis.net/ows/1.1",
        }
        result_layers = []
        for layer in root.findall(".//wmts:Layer", namespaces):
            identifier = layer.findtext("ows:Identifier", default="", namespaces=namespaces)
            if identifier not in LAYERS:
                continue
            time_default = None
            time_ranges = []
            for dimension in layer.findall("wmts:Dimension", namespaces):
                if dimension.findtext("ows:Identifier", default="", namespaces=namespaces) != "Time":
                    continue
                time_default = dimension.findtext("wmts:Default", default=None, namespaces=namespaces)
                time_ranges = [node.text for node in dimension.findall("wmts:Value", namespaces) if node.text]
                break
            matrix_set = next((
                node.findtext("wmts:TileMatrixSet", default="", namespaces=namespaces)
                for node in layer.findall("wmts:TileMatrixSetLink", namespaces)
            ), "")
            if not time_default or not matrix_set:
                continue
            result_layers.append({
                "id": identifier,
                "title": layer.findtext("ows:Title", default=identifier, namespaces=namespaces),
                "default_time": time_default,
                "time_ranges": time_ranges,
                "tile_matrix_set": matrix_set,
                "max_zoom": int(matrix_set.rsplit("Level", 1)[-1]) if "Level" in matrix_set else None,
                "formats": [node.text for node in layer.findall("wmts:Format", namespaces) if node.text],
            })
        if len(result_layers) != len(LAYERS):
            raise ValueError("NASA GIBS no devolvió todas las capas solicitadas.")
        _cache = {
            "provider": "NASA GIBS",
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "layers": result_layers,
            "interpretation": "Servicio de visualización WMTS; las teselas no son registros numéricos para entrenar modelos.",
        }
        _cache_until = time.monotonic() + 900
        return _cache
