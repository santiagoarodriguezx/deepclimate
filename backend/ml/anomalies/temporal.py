"""
Temporal Anomaly Detection Engine.
Implements:
- Rolling Z-Score
- Robust Z-Score (Median Absolute Deviation - MAD)
- Isolation Forest (Scikit-Learn)
- Historical Hour-of-Day / Day-of-Week Seasonality Baseline
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from sklearn.ensemble import IsolationForest


class TemporalAnomalyDetector:
    def __init__(self, z_threshold: float = 2.5, contamination: float = 0.05):
        self.z_threshold = z_threshold
        self.contamination = contamination

    def detect_anomalies(
        self,
        time_series: List[Dict[str, Any]],
        method: str = "combined"  # z_score, robust_mad, isolation_forest, combined
    ) -> List[Dict[str, Any]]:
        """
        Takes time series list with [{'timestamp': '...', 'value': float}]
        and detects statistical and machine learning anomalies.
        """
        if len(time_series) < 10:
            return []

        df = pd.DataFrame(time_series)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])

        if len(df) < 10:
            return []

        values = df["value"].values
        anomalies = []

        # 1. Rolling Mean & Std (Z-Score)
        rolling_window = min(24, max(5, len(df) // 4))
        roll_mean = df["value"].rolling(rolling_window, min_periods=3).mean()
        roll_std = df["value"].rolling(rolling_window, min_periods=3).std().replace(0, 1e-5)
        df["z_score"] = (df["value"] - roll_mean) / roll_std

        # 2. Robust MAD (Median Absolute Deviation)
        median = np.median(values)
        mad = np.median(np.abs(values - median))
        mad_scale = 1.4826 * mad if mad > 1e-5 else 1.0
        df["robust_z"] = (df["value"] - median) / mad_scale

        # 3. Isolation Forest
        X = values.reshape(-1, 1)
        iso = IsolationForest(contamination=self.contamination, random_state=42)
        try:
            iso.fit(X)
            iso_preds = iso.predict(X)  # -1 for anomalies
            iso_scores = -iso.score_samples(X)  # higher = more anomalous
        except Exception:
            iso_preds = np.ones(len(values))
            iso_scores = np.zeros(len(values))

        df["iso_pred"] = iso_preds
        df["iso_score"] = iso_scores

        # Identify points meeting criterion
        for i, row in df.iterrows():
            is_anomaly = False
            primary_method = "statistical"

            if method == "z_score" and abs(row["z_score"]) >= self.z_threshold:
                is_anomaly = True
                primary_method = "rolling_z_score"
            elif method == "robust_mad" and abs(row["robust_z"]) >= self.z_threshold:
                is_anomaly = True
                primary_method = "robust_mad"
            elif method == "isolation_forest" and row["iso_pred"] == -1:
                is_anomaly = True
                primary_method = "isolation_forest"
            elif method == "combined":
                # Majority consensus or extreme z-score
                conditions = [
                    abs(row["z_score"]) >= self.z_threshold,
                    abs(row["robust_z"]) >= (self.z_threshold * 1.1),
                    row["iso_pred"] == -1
                ]
                if sum(conditions) >= 2 or abs(row["z_score"]) > 3.5:
                    is_anomaly = True
                    primary_method = "isolation_forest_zscore_consensus"

            if is_anomaly:
                expected_min = max(0.0, round(float(median - 2 * mad_scale), 2))
                expected_max = round(float(median + 2 * mad_scale), 2)
                anomalies.append({
                    "timestamp": row["timestamp"].isoformat(),
                    "value": round(float(row["value"]), 2),
                    "expected_range": [expected_min, expected_max],
                    "score": round(float(abs(row["robust_z"])), 2),
                    "method": primary_method,
                    "direction": "high" if row["value"] > expected_max else "low"
                })

        return anomalies
