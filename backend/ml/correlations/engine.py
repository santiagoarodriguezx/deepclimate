"""
Environmental Correlation Engine.
Calculates Pearson, Spearman, and lagged cross-correlations between
atmospheric and pollutant variables (e.g. rain vs PM2.5 wash-off, wind vs PM10 dispersion).
Strictly respects non-causal language guidelines.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any
from scipy.stats import pearsonr, spearmanr


class CorrelationEngine:
    def calculate_correlation(
        self,
        series_a: List[Dict[str, Any]],
        series_b: List[Dict[str, Any]],
        name_a: str = "Variable A",
        name_b: str = "Variable B",
        max_lags: int = 6
    ) -> Dict[str, Any]:
        """
        Calculates correlation between two time series aligned by timestamp.
        Computes Pearson, Spearman, and lagged correlations (up to max_lags hours).
        """
        df_a = pd.DataFrame(series_a).rename(columns={"value": "val_a"})
        df_b = pd.DataFrame(series_b).rename(columns={"value": "val_b"})

        if df_a.empty or df_b.empty:
            return {
                "variables": [name_a, name_b],
                "status": "insufficient_data",
                "aligned_points": 0,
                "pearson": None,
                "spearman": None,
                "p_value": None,
                "statistically_significant": False,
                "relationship": "Datos insuficientes para establecer correlación.",
                "causality_disclaimer": "Recuerde que correlación no implica causalidad.",
                "lagged_correlations": []
            }

        df_a["timestamp"] = pd.to_datetime(df_a["timestamp"])
        df_b["timestamp"] = pd.to_datetime(df_b["timestamp"])

        merged = pd.merge(df_a, df_b, on="timestamp", how="inner").dropna()
        if len(merged) < 10:
            return {
                "variables": [name_a, name_b],
                "status": "insufficient_data",
                "aligned_points": len(merged),
                "pearson": None,
                "spearman": None,
                "p_value": None,
                "statistically_significant": False,
                "relationship": "Número insuficiente de observaciones coincidentes en el tiempo.",
                "causality_disclaimer": "Recuerde que correlación no implica causalidad.",
                "lagged_correlations": []
            }

        x = merged["val_a"].values
        y = merged["val_b"].values

        p_corr, p_val = pearsonr(x, y)
        s_corr, s_val = spearmanr(x, y)

        # Lagged cross correlations
        lagged = []
        for lag in range(1, max_lags + 1):
            if len(merged) > lag + 5:
                lag_x = x[:-lag]
                lag_y = y[lag:]
                r_lag, _ = pearsonr(lag_x, lag_y)
                lagged.append({
                    "lag_hours": lag,
                    "correlation": round(float(r_lag), 3)
                })

        # Relationship description using strictly non-causal language
        if abs(p_corr) < 0.2:
            rel = f"Existe una correlación lineal débil o nula ({round(p_corr, 2)}) entre {name_a} y {name_b}."
        elif p_corr <= -0.2:
            strength = "fuerte" if p_corr < -0.6 else "moderada"
            rel = f"Existe una correlación inversa {strength} ({round(p_corr, 2)}): incrementos en {name_a} se asocian temporalmente con disminuciones en {name_b}."
        else:
            strength = "fuerte" if p_corr > 0.6 else "moderada"
            rel = f"Existe una correlación positiva {strength} ({round(p_corr, 2)}): incrementos en {name_a} coinciden temporalmente con valores más elevados de {name_b}."

        return {
            "variables": [name_a, name_b],
            "status": "available",
            "aligned_points": len(merged),
            "pearson": round(float(p_corr), 3),
            "spearman": round(float(s_corr), 3),
            "p_value": float(f"{p_val:.2e}"),
            "statistically_significant": p_val < 0.05,
            "relationship": rel,
            "lagged_correlations": lagged,
            "causality_disclaimer": "Nota metodológica: Se reporta correlación estadística observada; no se afirma causalidad directa unidireccional."
        }
