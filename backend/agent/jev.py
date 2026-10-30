"""
Jev - Environmental Intelligence Reasoning Agent.
Coordinates multi-step tool execution, analyzes SIATA observations,
applies machine learning models, and synthesizes verifiable evidence-backed explanations.
Strictly respects non-causality, temporal honesty, and zero-hallucination principles.
"""

import time
import os
import json
import datetime
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.database.models import SourceRun
from backend.agent.tools.env_tools import EnvironmentalToolKit
from backend.agent.planner import QueryPlanner
from backend.agent.llm import configured_assistant

logger = logging.getLogger(__name__)


class JevAgent:
    MAX_STEPS = 8
    MAX_TOOL_CALLS = 15
    MAX_EXECUTION_TIME_SECONDS = 30.0

    SYSTEM_PROMPT = """Eres Jev, el cerebro de inteligencia ambiental de DeepClimate para el Valle de Aburrá.
Tu función es interpretar datos observacionales oficiales, ejecutar herramientas de machine learning y estadística, y comunicar hallazgos de forma rigurosa, clara y honesta.

REGLAS ESTRICTAS:
1. Cero alucinación: NUNCA inventes cifras, estaciones ni coordenadas. Todos los números deben originarse en los resultados de herramientas.
2. Honestidad temporal: Si el último dato disponible tiene minutos u horas de desfase, declara explícitamente: "El último dato disponible tiene aproximadamente X minutos/horas". NUNCA digas "ahora mismo" si el dato tiene rezago.
3. No afirmes causalidad sin evidencia: Usa "Existe una correlación estadística observada" en lugar de "X causa Y".
4. Claridad en calidad de datos: Si los datos provienen de sensores con código de calidad dudoso o no validado, acláralo al usuario.
5. Transparencia: Comunica siempre la evidencia observada (estaciones, periodo, modelos aplicados, frescura)."""

    def __init__(self, db: Session):
        self.db = db
        self.toolkit = EnvironmentalToolKit(db)
        self.planner = QueryPlanner()
        self.assistant, self.assistant_provider = configured_assistant()

    def process_query(self, user_query: str) -> Dict[str, Any]:
        """
        Executes multi-step reasoning loop:
        Query -> Plan -> Tool Execution -> Result Processing -> Evidence Synthesis
        """
        start_time = time.time()
        tool_execution_log = []
        collected_evidence = {
            "stations_consulted": set(),
            "variables": set(),
            "ml_models": set(),
            "freshness_notes": [],
            "anomalies_found": [],
            "events_found": []
        }

        # Generate execution plan
        plan = self.planner.plan_query(user_query)

        step_count = 0
        tool_call_count = 0

        tool_results = {}

        for step in plan:
            # Guard limits
            if step_count >= self.MAX_STEPS or tool_call_count >= self.MAX_TOOL_CALLS:
                break
            if (time.time() - start_time) > self.MAX_EXECUTION_TIME_SECONDS:
                break

            tool_name = step["tool"]
            tool_args = step.get("args", {})
            step_count += 1
            tool_call_count += 1

            # Dispatch tool call
            result = self._dispatch_tool(tool_name, tool_args)
            tool_results[tool_name] = result

            tool_execution_log.append({
                "step": step_count,
                "tool": tool_name,
                "args": tool_args,
                "status": "success" if "error" not in result else "error"
            })

            # Harvest evidence
            self._harvest_evidence(tool_name, result, collected_evidence)

        # Synthesize final natural language answer based strictly on evidence
        execution_latency_ms = int((time.time() - start_time) * 1000)
        answer = self._synthesize_answer(user_query, tool_results, collected_evidence)
        ai_provider, ai_model = "local_evidence_summary", None
        if self.assistant:
            try:
                llm_answer, llm_model = self.assistant.explain(user_query, self._compact_context(tool_results))
                if llm_answer:
                    answer, ai_provider, ai_model = llm_answer, self.assistant_provider, llm_model
            except Exception as exc:
                logger.warning("Remote explanation unavailable (%s); using local evidence summary.", type(exc).__name__)
                ai_provider = "local_fallback"
            execution = getattr(self.assistant, "last_execution", None)
            if execution:
                self._persist_remote_execution(self.assistant_provider or "remote_llm", execution)

        # Compile evidence report
        evidence_summary = {
            "stations": sorted(list(collected_evidence["stations_consulted"])),
            "variables": sorted(list(collected_evidence["variables"])),
            "ml_models_applied": sorted(list(collected_evidence["ml_models"])),
            "data_freshness": collected_evidence["freshness_notes"][0] if collected_evidence["freshness_notes"] else "Verificada",
            "active_anomalies_count": len(collected_evidence["anomalies_found"]),
            "tool_calls_executed": len(tool_execution_log),
            "execution_time_ms": execution_latency_ms
        }

        return {
            "query": user_query,
            "answer": answer,
            "evidence": evidence_summary,
            "steps": tool_execution_log,
            "ai_provider": ai_provider,
            "ai_model": ai_model,
        }

    def _persist_remote_execution(self, source_id: str, execution: dict) -> None:
        """Persist measured remote calls; a configured API key alone is not an inference."""
        try:
            started = datetime.datetime.fromisoformat(execution["started_at"].replace("Z", "+00:00"))
            finished = datetime.datetime.fromisoformat(execution["finished_at"].replace("Z", "+00:00"))
            self.db.add(SourceRun(
                source_id=source_id,
                started_at=started.replace(tzinfo=None),
                finished_at=finished.replace(tzinfo=None),
                status=execution["status"],
                records_count=1,
                latency_ms=execution["latency_ms"],
                error_message=execution.get("error"),
                metadata_json=json.dumps(execution, ensure_ascii=False, default=str),
            ))
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Could not persist remote AI execution metadata.")

    @staticmethod
    def _compact_context(results: dict) -> dict:
        compact = {}
        for name, result in results.items():
            if isinstance(result, dict):
                item = {key: value for key, value in result.items() if key != "stations"}
                for key, value in list(item.items()):
                    if isinstance(value, list):
                        item[key] = value[:12]
                compact[name] = item
            elif isinstance(result, list):
                compact[name] = result[:12]
            else:
                compact[name] = result
        # The request context has a fixed ceiling even for long station histories.
        encoded = json.dumps(compact, ensure_ascii=False, default=str)
        return json.loads(encoded[:12000]) if len(encoded) <= 12000 else {"summary": encoded[:12000]}

    def _dispatch_tool(self, name: str, args: dict) -> Any:
        try:
            if hasattr(self.toolkit, name):
                fn = getattr(self.toolkit, name)
                return fn(**args)
            else:
                return {"error": f"Tool '{name}' does not exist."}
        except Exception as e:
            return {"error": str(e)}

    def _harvest_evidence(self, tool_name: str, result: Any, evidence: dict):
        if not isinstance(result, dict) and not isinstance(result, list):
            return

        if tool_name == "get_stations" and isinstance(result, list):
            for s in result[:5]:
                evidence["stations_consulted"].add(s.get("name", s.get("code")))
        elif tool_name == "get_latest_observation" and isinstance(result, dict):
            st = result.get("station") or result.get("station_code")
            if st:
                evidence["stations_consulted"].add(st)
            if "variable" in result:
                evidence["variables"].add(result["variable"])
            if "freshness" in result and "human_lag" in result["freshness"]:
                evidence["freshness_notes"].append(f"Último dato {result['freshness']['human_lag']} ({result['freshness']['status']})")
        elif tool_name == "get_latest_by_variable" and isinstance(result, list):
            for r in result[:8]:
                evidence["stations_consulted"].add(r.get("station_name", r.get("station_code")))
            evidence["variables"].add("PM25")
        elif tool_name == "detect_anomalies" and isinstance(result, dict):
            evidence["ml_models"].add("Isolation Forest + Robust MAD")
            anoms = result.get("anomalies", [])
            evidence["anomalies_found"].extend(anoms)
        elif tool_name == "detect_spatial_anomalies" and isinstance(result, dict):
            evidence["ml_models"].add("Spatial Local Deviation (Haversine Z-score)")
            anoms = result.get("anomalies", [])
            evidence["anomalies_found"].extend(anoms)
        elif tool_name == "forecast_variable" and isinstance(result, dict):
            evidence["ml_models"].add(f"Forecasting: {result.get('model', 'Autoregressive Ridge')}")
        elif tool_name == "find_correlations" and isinstance(result, dict):
            evidence["ml_models"].add("Pearson & Spearman Lagged Correlation")
        elif tool_name == "get_active_events" and isinstance(result, list):
            evidence["events_found"].extend(result)
        elif tool_name in {"get_regional_forecast", "get_regional_history"} and isinstance(result, dict):
            if result.get("variable_id"):
                evidence["variables"].add(str(result["variable_id"]))
            if result.get("source_name"):
                evidence["ml_models"].add(str(result["source_name"]))
            if result.get("generated_at"):
                evidence["freshness_notes"].append(f"Pronóstico consultado {result['generated_at']}")
            elif result.get("latest_fetch_at"):
                evidence["freshness_notes"].append(f"Última captura del análisis {result['latest_fetch_at']}")

    def _synthesize_answer(self, query: str, results: dict, evidence: dict) -> str:
        """
        Synthesizes human-grade natural language explanation based strictly on tool results.
        Enforces SIATA Intelligence guidelines.
        """
        q_lower = query.lower()

        if "get_regional_forecast" in results:
            forecast = results["get_regional_forecast"]
            if forecast.get("status") != "available" or not forecast.get("forecast"):
                return f"No hay pronóstico regional disponible: {forecast.get('reason', 'Open-Meteo aún no publicó datos para esta consulta.')}"
            points = forecast["forecast"]
            values = [float(point["value"]) for point in points if isinstance(point.get("value"), (int, float))]
            if not values:
                return "El proveedor no devolvió valores numéricos para este pronóstico."
            variable = forecast.get("variable_id")
            unit = forecast.get("unit", "")
            if variable == "rain_probability":
                peak = max(points, key=lambda point: float(point.get("value", -1)))
                summary = f"La probabilidad máxima de precipitación en las próximas horas es **{peak['value']}%**, para el intervalo iniciado {peak['timestamp']} UTC."
            elif variable == "rain":
                summary = f"El modelo acumula **{sum(values):.1f} {unit}** en {len(values)} intervalos horarios consultados."
            elif variable == "temperature":
                summary = f"El rango horario pronosticado es **{min(values):.1f}–{max(values):.1f} {unit}** en {len(values)} intervalos."
            else:
                summary = f"El valor medio del pronóstico es **{sum(values) / len(values):.1f} {unit}** en {len(values)} intervalos."
            generated = forecast.get("generated_at")
            when = f" Capturado por la plataforma: {generated} UTC." if generated else ""
            return (
                f"{summary}\n\nFuente: **Open-Meteo Best Match**, punto de grilla "
                f"{forecast.get('latitude')}, {forecast.get('longitude')}. Es un pronóstico de modelo regional, "
                f"no una medición SIATA ni un pronóstico oficial de SIATA.{when}"
            )

        if "get_regional_history" in results:
            history = results["get_regional_history"]
            if history.get("status") != "available" or not history.get("series"):
                return f"No hay análisis regional disponible: {history.get('reason', 'NASA POWER no tiene datos publicados para el periodo.')}"
            values = [float(point["value"]) for point in history["series"]]
            unit = history.get("unit", "")
            dates = [point["timestamp"][:10] for point in history["series"]]
            if history.get("variable_id") == "rain":
                summary = f"NASA POWER reporta **{sum(values):.1f} {unit}** acumulados en {len(values)} días publicados; el promedio diario es {sum(values) / len(values):.1f} {unit}."
            else:
                summary = f"NASA POWER estima un promedio de **{sum(values) / len(values):.1f} {unit}** en {len(values)} días publicados, con rango {min(values):.1f}–{max(values):.1f} {unit}."
            fetched = history.get("latest_fetch_at")
            return (
                f"{summary}\n\nPeriodo disponible: **{dates[0]} a {dates[-1]}**. "
                "Es un análisis de modelo regional de resolución gruesa, con latencia propia del producto; "
                "no equivale a una estación ni al acumulado de pluviómetros SIATA. "
                f"Captura guardada: {fetched or 'sin marca de captura'} UTC."
            )

        # Case 1: Query about specific municipality / station status (e.g. Itagüí, Medellín)
        if "get_latest_observation" in results:
            obs = results["get_latest_observation"]
            st_name = obs.get("station", "la estación")
            val = obs.get("value")
            unit = obs.get("unit", "µg/m³")
            freshness = obs.get("freshness", {})
            lag_desc = freshness.get("human_lag", "reciente")

            comparison = results.get("compare_periods", {}).get("comparison", {})
            anomalies = results.get("detect_anomalies", {}).get("anomalies", [])

            lines = []
            if val is not None:
                lines.append(
                    f"En la estación **{st_name}**, la concentración registrada de PM2.5 es de **{val} {unit}**."
                )
                lines.append(f"El último dato disponible tiene una frescura de: **{lag_desc}** (estado {freshness.get('status', 'HEALTHY')}).")
            else:
                lines.append(f"No se cuenta con registro activo reciente para la estación solicitada.")

            period_1 = results.get("compare_periods", {}).get("period_1", {}).get("stats", {})
            period_2 = results.get("compare_periods", {}).get("period_2", {}).get("stats", {})
            enough_comparison_data = period_1.get("count", 0) >= 2 and period_2.get("count", 0) >= 2
            if comparison and enough_comparison_data:
                pct = comparison.get("percentage_change", 0.0)
                trend = comparison.get("trend", "estable")
                abs_diff = comparison.get("absolute_difference", 0.0)
                if abs(pct) > 3.0:
                    verb = "un incremento" if pct > 0 else "una reducción"
                    lines.append(
                        f"Al comparar con el período previo de 7 días, se observa {verb} del **{abs(pct)}%** "
                        f"(diferencia de {abs_diff:+.1f} {unit}, tendencia {trend})."
                    )
                else:
                    lines.append(f"El comportamiento se mantiene estable en relación con los últimos 7 días.")
            elif comparison:
                lines.append("No hay suficientes mediciones en ambos períodos para comparar la tendencia.")

            if anomalies:
                recent_anom = anomalies[-1]
                lines.append(
                    f"El detector de Machine Learning identificó una anomalía temporal con valor de **{recent_anom['value']} {unit}** "
                    f"(rango esperado: {recent_anom['expected_range'][0]} - {recent_anom['expected_range'][1]} {unit}, "
                    f"método: {recent_anom['method']})."
                )
            elif results.get("detect_anomalies", {}).get("status") == "insufficient_data":
                lines.append("No hay suficientes mediciones para evaluar anomalías temporales.")
            else:
                lines.append("No se detectaron anomalías temporales críticas en los últimos registros analizados.")

            return "\n\n".join(lines)

        # Case 2: General Valley anomalies & events ("¿está pasando algo extraño en el valle?")
        if "get_active_events" in results or "detect_spatial_anomalies" in results:
            events = results.get("get_active_events", [])
            spatial = results.get("detect_spatial_anomalies", {}).get("anomalies", [])
            rain_list = results.get("get_latest_by_variable", [])
            active_rain = [
                r for r in rain_list
                if r.get("value", 0) > 2.0
                and r.get("quality_status") not in {"unvalidated_unit", "retrieval_timestamp"}
            ]

            unique_events = []
            seen_event_keys = set()
            for event in events:
                key = (event.get("event_type"), tuple(sorted(event.get("station_ids", []))))
                if key not in seen_event_keys:
                    unique_events.append(event)
                    seen_event_keys.add(key)
            events = unique_events
            covered_station_ids = {
                station_id for event in events for station_id in event.get("station_ids", [])
            }
            spatial = [item for item in spatial if item.get("station_id") not in covered_station_ids]

            lines = []
            if not events and not spatial:
                spatial_result = results.get("detect_spatial_anomalies", {})
                if spatial_result.get("status") == "insufficient_data":
                    lines.append(f"No hay suficientes observaciones PM2.5 recientes y válidas para evaluar anomalías espaciales ({spatial_result.get('stations_evaluated', 0)} estaciones elegibles).")
                else:
                    lines.append("Tras inspeccionar las estaciones con lecturas recientes, **no encontré anomalías estadísticas críticas ni eventos activos**.")
            else:
                lines.append(f"He detectado **{len(events) + len(spatial)} evento(s) o anomalía(s)** que merecen atención:")
                for ev in events:
                    lines.append(f"- **{ev.get('title')}**: {ev.get('description')}")
                for sp in spatial:
                    lines.append(
                        f"- **Anomalía espacial en {sp['station_name']} ({sp['municipality']})**: "
                        f"Registra {sp['value']} µg/m³, mientras que sus {sp['neighbor_count']} estaciones vecinas "
                        f"promedian {sp['neighbor_mean']} µg/m³ (desviación local de {sp['local_deviation_score']}σ)."
                    )

            if active_rain:
                max_rain = max(r.get("value", 0) for r in active_rain)
                lines.append(f"Actualmente se registran precipitaciones en {len(active_rain)} estaciones (máximo acumulado: {max_rain} mm).")

            freshness_rep = results.get("get_data_freshness", {})
            if freshness_rep:
                online = freshness_rep.get("stations_online", 0)
                total = freshness_rep.get("total_stations", 0)
                lines.append(f"Disponibilidad de la red: **{online} de {total} estaciones activas en tiempo real**.")

            return "\n\n".join(lines)

        # Case 3: Correlation analysis
        if "find_correlations" in results:
            corr = results["find_correlations"]
            if corr.get("status") == "insufficient_data":
                return "**Análisis de relación ambiental:**\n\n" + corr.get("relationship", "Datos insuficientes para establecer correlación.") + f"\n\nObservaciones coincidentes: {corr.get('aligned_points', 0)}; se requieren al menos 10."
            lines = [
                f"**Análisis de Relación Ambiental ({corr.get('variables', ['Var A', 'Var B'])[0]} vs {corr.get('variables', ['Var A', 'Var B'])[1]}):**",
                corr.get("relationship", ""),
                f"- Coeficiente de Pearson: **{corr.get('pearson')}**",
                f"- Coeficiente de Spearman: **{corr.get('spearman')}**",
                f"- Significancia estadística (p-value): **{corr.get('p_value')}** ({'Significativo' if corr.get('statistically_significant') else 'No concluyente'})",
                f"*{corr.get('causality_disclaimer')}*"
            ]
            return "\n\n".join(lines)

        # Case 4: Forecasting
        if "forecast_variable" in results:
            fc = results["forecast_variable"]
            if fc.get("status") != "available" or not fc.get("forecast"):
                return f"No hay pronóstico disponible: {fc.get('status', 'el modelo no está entrenado')}. Entrena un modelo cuando exista suficiente historial horario validado."
            metric = fc.get("metrics", {})
            points = fc.get("forecast", [])
            first_p = points[0] if points else {}
            last_p = points[-1] if points else {}

            lines = [
                f"**Pronóstico de {fc.get('variable_id', 'Variable')} a {fc.get('horizon_hours', 24)} horas:**",
                f"El modelo ({fc.get('model')}) proyecta un valor inicial de **{first_p.get('prediction', 'N/A')} µg/m³** "
                f"(intervalo de incertidumbre al 95%: [{first_p.get('lower')}, {first_p.get('upper')}]) "
                f"y un valor hacia el final del horizonte de **{last_p.get('prediction', 'N/A')} µg/m³** "
                f"(rango [{last_p.get('lower')}, {last_p.get('upper')}]).",
                f"Métricas de validación empírica: **MAE = {metric.get('mae')}**, **RMSE = {metric.get('rmse')}**, **R² = {metric.get('r2')}**."
            ]
            return "\n\n".join(lines)

        # Generic summary
        return "He consultado los datos actualizados del SIATA y procesado los modelos analíticos solicitados. Consulte el bloque de evidencia para ver los detalles verificables."
