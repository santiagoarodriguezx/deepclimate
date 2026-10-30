"""Source registry: contracts and operating status are explicit and provenance-aware."""

import datetime
import os
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from backend.agent.decision import JevDecisionEngine
from backend.database.models import RegionalDatum, SourceRun


CATALOG = [
    {
        "id": "siata",
        "name": "SIATA · estaciones del Valle de Aburrá",
        "category": "observations",
        "url": "https://siata.gov.co/data/siata_app/",
        "variables": ["PM2.5", "PM10", "meteorología", "lluvia", "nivel de quebradas"],
        "temporal_resolution": "Depende del feed; se preserva la hora del sensor cuando se publica",
        "spatial_resolution": "Estaciones con coordenadas publicadas por SIATA",
        "update_frequency": "5 min · scheduler backend",
        "latency": "Variable por feed y estación; el dashboard expone frescura observada",
        "license": "Fuente oficial; respetar términos y atribución SIATA",
        "integration": "ingested",
    },
    {
        "id": "open_meteo",
        "name": "Open-Meteo · pronóstico regional Best Match",
        "category": "model_forecast",
        "url": "https://api.open-meteo.com/v1/forecast",
        "variables": ["temperatura", "humedad", "precipitación", "probabilidad de lluvia", "nubosidad", "viento", "presión"],
        "temporal_resolution": "1 h de salida API; el paso nativo puede ser mayor",
        "spatial_resolution": "Celda y modelo seleccionados por el proveedor; coordenadas devueltas en cada respuesta",
        "update_frequency": "Cada 3 h · scheduler backend",
        "latency": "Pronóstico operacional del proveedor; la inicialización exacta no viene en la respuesta consultada",
        "license": "Atribución Open-Meteo; revisar condiciones vigentes antes de uso comercial",
        "integration": "ingested",
    },
    {
        "id": "nasa_power",
        "name": "NASA POWER · análisis meteorológico diario",
        "category": "regional_analysis",
        "url": "https://power.larc.nasa.gov/api/temporal/daily/point",
        "variables": ["temperatura", "humedad", "precipitación", "radiación solar", "viento", "presión"],
        "temporal_resolution": "Diaria",
        "spatial_resolution": "Aproximadamente 0.5° × 0.625° para meteorología; celda real devuelta por NASA",
        "update_frequency": "Diaria · ventana móvil de 14 días con dos días de margen",
        "latency": "Histórico MERRA-2 mensual; GEOS-IT cercano a tiempo real con cerca de 2 días de latencia",
        "license": "NASA POWER; atribuir NASA POWER y proveedor de datos",
        "integration": "ingested",
    },
    {
        "id": "nasa_gibs",
        "name": "NASA GIBS · imágenes satelitales",
        "category": "visualization",
        "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/",
        "variables": ["reflectancia visible MODIS Terra", "capas de imagen satelital"],
        "temporal_resolution": "Por producto; MODIS True Color diario",
        "spatial_resolution": "Depende del producto y nivel de zoom",
        "update_frequency": "Tiles consultados bajo demanda",
        "latency": "Fecha disponible expuesta por la dimensión temporal del producto",
        "license": "NASA Earthdata GIBS; atribución visible en el mapa",
        "integration": "visualization_only",
    },
    {
        "id": "nasa_gpm",
        "name": "NASA GPM IMERG Early · estimación satelital de precipitación",
        "category": "satellite_precipitation",
        "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate_30min/",
        "variables": ["tasa estimada de precipitación"],
        "temporal_resolution": "30 min",
        "spatial_resolution": "0.1° × 0.1° (aprox. 10 km)",
        "update_frequency": "Visualización GIBS; producto Early con latencia nominal cercana a 4 h",
        "latency": "Aproximadamente 4 h para Early; sujeto a publicación del proveedor",
        "license": "NASA GPM; citar dataset IMERG y DOI de la versión usada",
        "integration": "visualization_only",
    },
    {
        "id": "ideam_radar",
        "name": "IDEAM · archivo de radares meteorológicos",
        "category": "radar_archive",
        "url": "https://s3-radaresideam.s3.us-east-1.amazonaws.com/",
        "variables": ["reflectividad", "velocidad radial", "variables polarimétricas en volúmenes RAW"],
        "temporal_resolution": "Volúmenes nominales cada 5 min",
        "spatial_resolution": "Volumen Level II; geometría específica por radar y barrido",
        "update_frequency": "Sondeo automático de metadatos cada 6 h",
        "latency": "Archivo histórico con aproximadamente 1 día de retraso; no se trata como radar operativo en vivo",
        "license": "CC BY 4.0 · atribución IDEAM",
        "integration": "metadata_only",
    },
    {
        "id": "copernicus_cds",
        "name": "Copernicus Climate Data Store",
        "category": "reanalysis_candidate",
        "url": "https://cds.climate.copernicus.eu/",
        "variables": ["ERA5 / ERA5-Land, sujeto a producto y licencia"],
        "temporal_resolution": "Por dataset",
        "spatial_resolution": "Por dataset; no se ha ingerido",
        "update_frequency": "No programada",
        "latency": "No medido en este proyecto",
        "license": "Revisar licencia y condiciones por dataset",
        "integration": "not_integrated",
        "limitation": "Sin cliente configurado ni credenciales CDS verificadas; no se presenta como fuente conectada.",
    },
    {
        "id": "noaa_ncei",
        "name": "NOAA NCEI · estaciones globales",
        "category": "observation_candidate",
        "url": "https://www.ncei.noaa.gov/access",
        "variables": ["Dependen de estaciones con cobertura utilizable"],
        "temporal_resolution": "Por dataset",
        "spatial_resolution": "Estaciones; no se confirmó una serie local adecuada",
        "update_frequency": "No programada",
        "latency": "No medido en este proyecto",
        "license": "Por dataset",
        "integration": "not_integrated",
        "limitation": "No se validó una estación cercana con datos horarios completos para Medellín.",
    },
    {
        "id": "nvidia_nim",
        "name": "NVIDIA NIM · inferencia hospedada por API",
        "category": "ai_explanation",
        "url": "https://docs.api.nvidia.com/nim/reference/llm-apis",
        "variables": ["Explicación de evidencia verificada"],
        "temporal_resolution": "No aplica; interpreta resultados ya consultados",
        "spatial_resolution": "No genera datos meteorológicos ni predicciones locales",
        "update_frequency": "Bajo demanda al consultar Jev",
        "latency": "Servicio remoto; depende de NVIDIA API",
        "license": "Sujeto a términos de NVIDIA API y al modelo seleccionado",
        "integration": "remote_api",
        "limitation": (
            "Solo explica evidencia del proyecto. No ejecuta pesos localmente ni sustituye modelos de pronóstico. "
            "La pregunta y la evidencia resumida se envían al servicio remoto. La API de CorrDiff cubre CONUS; "
            "FourCastNet requiere entradas atmosféricas globales validadas."
        ),
    },
]


def get_source_catalog(db: Session) -> dict:
    latest_runs = {}
    for run in db.query(SourceRun).order_by(desc(SourceRun.finished_at), desc(SourceRun.id)).all():
        latest_runs.setdefault(run.source_id, run)
    counts = dict(
        db.query(RegionalDatum.source_id, func.count(RegionalDatum.id))
        .group_by(RegionalDatum.source_id).all()
    )
    last_values = dict(
        db.query(RegionalDatum.source_id, func.max(RegionalDatum.valid_at))
        .group_by(RegionalDatum.source_id).all()
    )

    items = []
    for item in CATALOG:
        result = dict(item)
        run_key = "ideam_radar" if item["id"] == "ideam_radar" else item["id"]
        run = latest_runs.get(run_key)
        if item["integration"] in {"ingested", "metadata_only"}:
            result["status"] = "scheduled"
            if run:
                result["status"] = "error" if run.status == "failed" else run.status
                result["last_run"] = run.to_dict()
        elif item["integration"] == "visualization_only":
            result["status"] = "available"
            result["last_run"] = None
        elif item["integration"] == "remote_api":
            result["status"] = "configured" if os.getenv("NVIDIA_API_KEY", "").strip() else "not_configured"
            result["last_run"] = None
        else:
            result["status"] = "not_integrated"
            result["last_run"] = None
        if item["id"] == "siata":
            scan = latest_runs.get("siata_discovery")
            scan_data = scan.to_dict() if scan else None
            if scan_data and not (scan_data.get("error_message") or "").strip():
                scan_data["error_message"] = None
            result["availability_scan"] = scan_data
        result["records_stored"] = int(counts.get(item["id"], 0))
        result["latest_valid_time"] = last_values[item["id"]].isoformat() if item["id"] in last_values else None
        items.append(result)

    return {
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sources": items,
        "decision_provider": JevDecisionEngine.provider_status(),
    }
