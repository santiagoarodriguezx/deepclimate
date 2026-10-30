"""
SIATA Source Discovery Module.
Discovers and catalogizes official SIATA endpoints, layers, JSON feeds, and historical archives.
Prevents inventing endpoints: All sources are validated against verified SIATA infrastructure.
"""

import os
import json
import re
import datetime
from typing import Dict, Any, List
from backend.ingestion.siata.client import SiataClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CATALOG_PATH = os.path.join(BASE_DIR, "data", "source_catalog.json")


class SiataDiscovery:
    def __init__(self, timeout: float = 4.0):
        self.client = SiataClient(
            headers={"User-Agent": "SIATA-Intelligence/1.0 (environmental research)"},
            timeout=timeout,
            transport_retries=0,
            retry_attempts=1,
        )

    def scan_sources(self) -> Dict[str, Any]:
        """
        Scans all official SIATA portals, directories, and endpoints.
        Produces a verified catalog of active sources.
        """
        now = datetime.datetime.utcnow().isoformat()
        catalog = {
            "version": "1.0.0",
            "last_discovered": now,
            "sources": []
        }

        # 1. Real-time Air Quality Layer (POECA Stations)
        catalog["sources"].append({
            "id": "siata_air_quality_poeca",
            "name": "Red de Calidad del Aire - Estaciones POECA (PM2.5)",
            "type": "realtime",
            "frequency_seconds": 300,
            "format": "json",
            "url": "https://siata.gov.co/siata_nuevo/index.php/capa_service/consultar_capa_carga",
            "method": "POST",
            "payload": {"id_capa": "C_00000000000000000000602"},
            "variables": ["PM25", "ICA"],
            "status": self._probe_post(
                "https://siata.gov.co/siata_nuevo/index.php/capa_service/consultar_capa_carga",
                {"id_capa": "C_00000000000000000000602"}
            )
        })

        # 2. Real-time Air Quality Layer (Non-POECA Stations)
        catalog["sources"].append({
            "id": "siata_air_quality_no_poeca",
            "name": "Red de Calidad del Aire - Estaciones NO POECA (PM2.5)",
            "type": "realtime",
            "frequency_seconds": 300,
            "format": "json",
            "url": "https://siata.gov.co/siata_nuevo/index.php/capa_service/consultar_capa_carga",
            "method": "POST",
            "payload": {"id_capa": "C_00000000000000000000603"},
            "variables": ["PM25", "ICA"],
            "status": self._probe_post(
                "https://siata.gov.co/siata_nuevo/index.php/capa_service/consultar_capa_carga",
                {"id_capa": "C_00000000000000000000603"}
            )
        })

        # 3. Real-time Meteorology Feed (PluviometricaMeteo.json)
        catalog["sources"].append({
            "id": "siata_meteo_realtime",
            "name": "Red Meteorológica y Pluviométrica SIATA",
            "type": "realtime",
            "frequency_seconds": 180,
            "format": "json",
            "url": "https://siata.gov.co/data/siata_app/PluviometricaMeteo.json",
            "method": "GET",
            "variables": ["temperature", "humidity", "pressure", "wind_speed", "wind_direction", "rain"],
            "status": self._probe_get("https://siata.gov.co/data/siata_app/PluviometricaMeteo.json")
        })

        # 4. Real-time Pluviometric Network Feed (Pluviometrica.json)
        catalog["sources"].append({
            "id": "siata_rain_realtime",
            "name": "Red de Pluviómetros del Valle de Aburrá",
            "type": "realtime",
            "frequency_seconds": 300,
            "format": "json",
            "url": "https://siata.gov.co/data/siata_app/Pluviometrica.json",
            "method": "GET",
            "variables": ["rain"],
            "status": self._probe_get("https://siata.gov.co/data/siata_app/Pluviometrica.json")
        })

        # 5. Real-time Stream Level Network (Nivel.json)
        catalog["sources"].append({
            "id": "siata_stream_level_realtime",
            "name": "Red de Sensores de Nivel de Quebradas y Río Medellín",
            "type": "realtime",
            "frequency_seconds": 300,
            "format": "json",
            "url": "https://siata.gov.co/data/siata_app/Nivel.json",
            "method": "GET",
            "variables": ["river_level"],
            "status": self._probe_get("https://siata.gov.co/data/siata_app/Nivel.json")
        })

        # 6. Station Freshness Verification Page
        catalog["sources"].append({
            "id": "siata_air_freshness_verifier",
            "name": "Monitor de Verificación de Frescura Red de Aire SIATA",
            "type": "hourly",
            "frequency_seconds": 600,
            "format": "html_table",
            "url": "https://siata.gov.co/CalidadAire/verificacionEstacionesRedAireValidadoSIATA.php",
            "method": "GET",
            "variables": ["PM25", "PM10", "O3", "NO", "NO2", "CO", "SO2"],
            "status": self._probe_get("https://siata.gov.co/CalidadAire/verificacionEstacionesRedAireValidadoSIATA.php")
        })

        # 7. Official Station Inventory File
        catalog["sources"].append({
            "id": "siata_station_inventory",
            "name": "Inventario Oficial de Estaciones de Calidad del Aire",
            "type": "daily",
            "frequency_seconds": 86400,
            "format": "csv",
            "url": "https://siata.gov.co/CalidadAire/cadatos/Estaciones.txt",
            "method": "GET",
            "variables": ["station_metadata"],
            "status": self._probe_get("https://siata.gov.co/CalidadAire/cadatos/Estaciones.txt")
        })

        # 8. Historical Dataset Directory (IDEAM)
        historical_zips = self.discover_historical_archives()
        catalog["sources"].append({
            "id": "siata_historical_ideam",
            "name": "Repositorio Histórico de Datos Validados SIATA / IDEAM",
            "type": "historical",
            "frequency_seconds": 86400,
            "format": "zip_xls",
            "url": "https://siata.gov.co/IDEAM/",
            "method": "GET",
            "discovered_archives_count": len(historical_zips),
            "latest_archives": historical_zips[-10:],
            "status": "active" if historical_zips else "offline"
        })

        # Save to catalog file
        os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)

        return catalog

    def discover_historical_archives(self) -> List[Dict[str, str]]:
        """
        Dynamically crawls https://siata.gov.co/IDEAM/ to discover available monthly archive zips.
        Avoids hardcoding file names.
        """
        url = "https://siata.gov.co/IDEAM/"
        try:
            resp = self.client.get(url)
            if resp.status_code != 200:
                return []
            links = re.findall(r'href=["\'](DatosValidados_[^"\']+\.zip)["\']', resp.text, re.IGNORECASE)
            # Remove duplicates preserving order
            unique_links = []
            seen = set()
            for l in links:
                if l not in seen:
                    seen.add(l)
                    unique_links.append({
                        "filename": l,
                        "url": f"https://siata.gov.co/IDEAM/{l}"
                    })
            return unique_links
        except Exception:
            return []

    def _probe_get(self, url: str) -> str:
        try:
            resp = self.client.get(url)
            if url.lower().endswith(".json"):
                data = resp.json()
                if not isinstance(data, dict) or not isinstance(data.get("estaciones"), list):
                    return "invalid_schema"
            elif url.endswith("Estaciones.txt"):
                if "Nombre" not in resp.text or "Latitud" not in resp.text:
                    return "invalid_schema"
            elif "/IDEAM/" in url and not re.search(r"DatosValidados_[^\"']+\.zip", resp.text, re.IGNORECASE):
                return "no_archives"
            return "active"
        except Exception:
            return "offline"

    def _probe_post(self, url: str, data: dict) -> str:
        try:
            resp = self.client.post(url, data=data, headers={"X-Requested-With": "XMLHttpRequest"})
            payload = resp.json()
            return "active" if payload.get("status") == "ok" and isinstance(payload.get("feature_vector"), list) else "invalid_schema"
        except Exception:
            return "offline"

    def close(self):
        self.client.close()
