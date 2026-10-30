"""
Alert Engine and Environmental Event Detector.
Detects multi-station anomalies, persistence episodes, and sudden environmental shifts.
Follows the deterministic event generation principle:
Rules and ML models generate the event -> Jev interprets and explains the evidence.
"""

import datetime
import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.database.repository import EnvironmentalRepository
from backend.database.models import EnvironmentalEvent
from backend.monitoring.freshness import INVALID_OBSERVATION_QUALITY, is_recent_observation
from backend.ml.anomalies.spatial import SpatialAnomalyDetector
from backend.ml.anomalies.temporal import TemporalAnomalyDetector


class AlertEngine:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EnvironmentalRepository(db)
        self.spatial_detector = SpatialAnomalyDetector()
        self.temporal_detector = TemporalAnomalyDetector()

    def evaluate_events(self) -> List[Dict[str, Any]]:
        """
        Executes full valley surveillance sweep across all active stations.
        Generates and stores detected events with verifiable evidence.
        """
        detected_events = []
        now = datetime.datetime.utcnow()

        # 1. Evaluate measured PM2.5 observations from air-quality stations.
        latest_pm25 = [
            row for row in self.repo.get_latest_by_variable("PM25")
            if row["station_type"] == "air_quality"
            and row["quality_status"] not in INVALID_OBSERVATION_QUALITY
            and is_recent_observation(row.get("observed_at"))
        ]
        if len(latest_pm25) >= 3:
            # Check spatial anomalies
            spatial_anoms = self.spatial_detector.detect_spatial_anomalies(latest_pm25)
            for anom in spatial_anoms:
                evt_data = {
                    "event_type": "spatial_anomaly",
                    "severity": "high" if abs(anom["local_deviation_score"]) > 3.0 else "medium",
                    "title": f"Anomalía Espacial Localizada en {anom['station_name']} ({anom['municipality']})",
                    "description": (
                        f"La estación {anom['station_name']} registra {anom['value']} µg/m³, "
                        f"mientras que las estaciones cercanas promedian {anom['neighbor_mean']} µg/m³ "
                        f"(desviación local de {anom['local_deviation_score']}σ)."
                    ),
                    "detected_at": now,
                    "station_ids": [anom["station_id"]],
                    "evidence": anom
                }
                detected_events.append(evt_data)

            # Check cluster episode: multiple stations in same municipality with high PM2.5 (>35)
            high_stations = [s for s in latest_pm25 if s["value"] >= 35.0]
            if len(high_stations) >= 2:
                # Group by municipality
                muni_groups = {}
                for s in high_stations:
                    m = s.get("municipality", "Valle de Aburrá")
                    muni_groups.setdefault(m, []).append(s)

                for muni, st_list in muni_groups.items():
                    if len(st_list) >= 2:
                        avg_val = round(sum(s["value"] for s in st_list) / len(st_list), 1)
                        evt_data = {
                            "event_type": "air_quality_anomaly",
                            "severity": "high" if avg_val > 55.0 else "medium",
                            "title": f"Episodio de Calidad del Aire en {muni} ({len(st_list)} estaciones elevadas)",
                            "description": (
                                f"{len(st_list)} estaciones en {muni} registran concentraciones concurrentes "
                                f"de PM2.5 superiores a la norma (promedio {avg_val} µg/m³)."
                            ),
                            "detected_at": now,
                            "station_ids": [s["station_id"] for s in st_list],
                            "evidence": {
                                "municipality": muni,
                                "average_pm25": avg_val,
                                "stations": [
                                    {"id": s["station_id"], "name": s["station_name"], "value": s["value"]}
                                    for s in st_list
                                ]
                            }
                        }
                        detected_events.append(evt_data)

        # 2. Evaluate Rain Episodes
        latest_rain = self.repo.get_latest_by_variable("rain")
        active_rain_stations = [
            s for s in latest_rain
            if s["value"] > 5.0
            and s["quality_status"] not in INVALID_OBSERVATION_QUALITY
            and is_recent_observation(s.get("observed_at"))
        ]
        if len(active_rain_stations) >= 3:
            max_rain = max(s["value"] for s in active_rain_stations)
            evt_data = {
                "event_type": "rain_event",
                "severity": "high" if max_rain > 30.0 else "medium",
                "title": f"Evento de Precipitación Generalizado ({len(active_rain_stations)} sensores activos)",
                "description": (
                    f"Se registran precipitaciones significativas en {len(active_rain_stations)} estaciones del Valle de Aburrá, "
                    f"con un acumulado máximo de {max_rain} mm."
                ),
                "detected_at": now,
                "station_ids": [s["station_id"] for s in active_rain_stations],
                "evidence": {
                    "active_rain_stations_count": len(active_rain_stations),
                    "maximum_rain_mm": max_rain,
                    "stations": [
                        {"id": s["station_id"], "name": s["station_name"], "rain_mm": s["value"]}
                        for s in active_rain_stations[:5]
                    ]
                }
            }
            detected_events.append(evt_data)

        return self._persist_current_events(detected_events)

    def _persist_current_events(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Refresh current alerts, deactivate resolved ones, and avoid duplicate active events."""
        event_types = {"spatial_anomaly", "air_quality_anomaly", "rain_event"}
        existing = self.db.query(EnvironmentalEvent).filter(
            EnvironmentalEvent.active == True,
            EnvironmentalEvent.event_type.in_(event_types),
        ).order_by(EnvironmentalEvent.detected_at.desc()).all()

        def event_key(event_type, station_ids):
            return event_type, tuple(sorted(station_ids or []))

        pending = {
            event_key(candidate["event_type"], candidate["station_ids"]): candidate
            for candidate in candidates
        }
        kept = set()
        for event in existing:
            key = event_key(event.event_type, json.loads(event.station_ids_json or "[]"))
            candidate = pending.get(key)
            if candidate and key not in kept:
                event.title = candidate["title"]
                event.description = candidate["description"]
                event.severity = candidate["severity"]
                event.evidence_json = json.dumps(candidate["evidence"], ensure_ascii=False)
                kept.add(key)
            else:
                event.active = False
        self.db.commit()

        new_events = []
        for key, candidate in pending.items():
            if key not in kept:
                self.repo.record_event(candidate)
                new_events.append(candidate)
        return new_events
