"""
Query Planner for Jev Agent.
Analyzes user intent and generates structured, decomposed execution plans.
Translates complex queries into ordered tool sequences.
"""

import re
from typing import Dict, Any, List


class QueryPlanner:
    def plan_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Decomposes a user query into a sequence of executable tool actions.
        """
        q = query.lower()
        plan = []

        # 1. Detect Municipality
        municipalities = [
            "itagüí", "itagui", "medellín", "medellin", "bello", "envigado",
            "sabaneta", "caldas", "la estrella", "copacabana", "girardota", "barbosa"
        ]
        target_muni = None
        for m in municipalities:
            if m in q:
                target_muni = m.capitalize().replace("Itagui", "Itagüí").replace("Medellin", "Medellín")
                break

        # 2. Specific intent: "algo extraño", "anomalías", "resumen valle", "cómo está el valle"
        if any(w in q for w in ["extraño", "anomalía", "anomalia", "atención", "emergencia", "pasa algo", "resumen ambiental"]):
            plan.append({"tool": "get_data_freshness", "args": {"variable_id": "PM25"}})
            plan.append({"tool": "get_active_events", "args": {}})
            plan.append({"tool": "detect_spatial_anomalies", "args": {"variable_id": "PM25"}})
            plan.append({"tool": "get_latest_by_variable", "args": {"variable_id": "rain"}})
            return plan

        # 3. Intent: Correlación / relación entre variables
        if any(w in q for w in ["correlación", "correlacion", "relación", "relacion", "lluvia y pm", "viento y pm"]):
            st_id = "ITA-CJUS" if target_muni == "Itagüí" else "MED-PJIC"
            plan.append({"tool": "find_correlations", "args": {"station_id": st_id, "var_a": "rain", "var_b": "PM25", "days": 14}})
            return plan

        weather_intent = any(w in q for w in [
            "lluvia", "llover", "llov", "precipit", "temperatura", "humedad",
            "viento", "nubosidad", "clima", "meteorolog", "va a llover",
        ])
        if weather_intent and any(w in q for w in ["últim", "ultim", "históric", "histor", "comportado", "semana pasada"]):
            variable_id = self._weather_variable(q)
            plan.append({"tool": "get_regional_history", "args": {"variable_id": variable_id, "days": 7}})
            return plan

        if weather_intent:
            variable_id = self._weather_variable(q, forecast=True)
            plan.append({"tool": "get_regional_forecast", "args": {"variable_id": variable_id, "hours": 24}})
            return plan

        # 4. Intent: Pronóstico / predicción
        if any(w in q for w in ["pronóstico", "pronostico", "predecir", "predice", "mañana", "futuro"]):
            st_id = "ITA-CJUS" if target_muni == "Itagüí" else "MED-PJIC"
            plan.append({"tool": "forecast_variable", "args": {"station_id": st_id, "variable_id": "PM25", "horizon_hours": 24}})
            return plan

        # 5. Intent: Calidad del aire / PM2.5 en un municipio o estación
        if target_muni:
            plan.append({"tool": "get_stations", "args": {"municipality": target_muni, "station_type": "air_quality"}})
            # We will dynamically chain the primary station
            st_code = "ITA-CJUS" if target_muni == "Itagüí" else (
                "ENV-HOSP" if target_muni == "Envigado" else (
                    "BEL-USBV" if target_muni == "Bello" else "MED-PJIC"
                )
            )
            plan.append({"tool": "get_latest_observation", "args": {"station_id": st_code, "variable_id": "PM25"}})
            plan.append({"tool": "get_time_series", "args": {"station_id": st_code, "variable_id": "PM25", "days": 7, "aggregation": "hour"}})
            plan.append({"tool": "compare_periods", "args": {"station_id": st_code, "variable_id": "PM25", "days_window": 7}})
            plan.append({"tool": "detect_anomalies", "args": {"station_id": st_code, "variable_id": "PM25", "days": 30}})
            return plan

        # 6. General status / "cómo está ahora"
        plan.append({"tool": "get_data_freshness", "args": {"variable_id": "PM25"}})
        plan.append({"tool": "get_latest_by_variable", "args": {"variable_id": "PM25"}})
        plan.append({"tool": "detect_spatial_anomalies", "args": {"variable_id": "PM25"}})
        return plan

    @staticmethod
    def _weather_variable(query: str, forecast: bool = False) -> str:
        q = query.lower()
        if any(w in q for w in ["temperatura", "temperatur", "calor", "frío", "frio"]):
            return "temperature"
        if "humedad" in q:
            return "humidity"
        if "viento" in q:
            return "wind_speed"
        if any(w in q for w in ["nubosidad", "nubes", "nublado"]):
            return "cloud_cover"
        if forecast and any(w in q for w in ["probabilidad", "va a llover", "llover", "llov"]):
            return "rain_probability"
        return "rain"
