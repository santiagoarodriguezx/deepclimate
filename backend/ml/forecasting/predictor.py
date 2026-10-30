"""Train and evaluate a small autoregressive Ridge model on observed hourly data."""

import datetime
import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


FEATURES = ["hour", "dayofweek", "lag_1", "lag_2", "lag_24", "rolling_mean_6"]
MIN_HOURLY_POINTS = 72


class EnvironmentalForecaster:
    def train(self, time_series: list[dict[str, Any]]) -> dict[str, Any]:
        df = pd.DataFrame(time_series)
        if df.empty or not {"timestamp", "value"}.issubset(df.columns):
            return {"status": "insufficient_data", "reason": "No hay una serie temporal utilizable."}

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["timestamp", "value"])
        df = df[np.isfinite(df["value"])].drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
        if df.empty:
            return {"status": "insufficient_data", "reason": "La serie no contiene valores válidos."}

        # A long gap breaks the sequence; train only on the latest continuous hourly run.
        gaps = df["timestamp"].diff().ne(pd.Timedelta(hours=1))
        df = df.loc[gaps.iloc[::-1].idxmax():].reset_index(drop=True)
        if len(df) < MIN_HOURLY_POINTS:
            return {
                "status": "insufficient_data",
                "reason": f"Se requieren {MIN_HOURLY_POINTS} horas consecutivas; hay {len(df)}.",
                "training_points": len(df),
            }

        df["hour"] = df["timestamp"].dt.hour
        df["dayofweek"] = df["timestamp"].dt.dayofweek
        df["lag_1"] = df["value"].shift(1)
        df["lag_2"] = df["value"].shift(2)
        df["lag_24"] = df["value"].shift(24)
        df["rolling_mean_6"] = df["value"].shift(1).rolling(6).mean()
        clean = df.dropna().reset_index(drop=True)
        split = max(1, int(len(clean) * 0.8))
        if split < 2 or len(clean) - split < 2:
            return {"status": "insufficient_data", "reason": "No hay suficientes puntos para validación temporal."}

        x = clean[FEATURES].to_numpy(dtype=float)
        y = clean["value"].to_numpy(dtype=float)
        validation_model = Ridge(alpha=1.0).fit(x[:split], y[:split])
        predictions = np.maximum(0, validation_model.predict(x[split:]))
        actual = y[split:]
        baseline = clean["lag_1"].to_numpy(dtype=float)[split:]
        residuals = actual - predictions
        mae = float(mean_absolute_error(actual, predictions))
        baseline_mae = float(mean_absolute_error(actual, baseline))

        model = Ridge(alpha=1.0).fit(x, y)
        return {
            "status": "trained",
            "model": "ridge_autoregressive_hourly_v1",
            "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "training_points": len(x),
            "validation_points": len(actual),
            "train_start": clean["timestamp"].iloc[0].isoformat(),
            "train_end": clean["timestamp"].iloc[split - 1].isoformat(),
            "metrics": {
                "mae": round(mae, 4),
                "rmse": round(float(np.sqrt(mean_squared_error(actual, predictions))), 4),
                "r2": round(float(r2_score(actual, predictions)), 4) if len(actual) > 2 else None,
                "baseline_mae": round(baseline_mae, 4),
                "improvement_over_baseline_pct": round((baseline_mae - mae) / baseline_mae * 100, 2) if baseline_mae else None,
            },
            "artifact": {
                "features": FEATURES,
                "coefficients": model.coef_.tolist(),
                "intercept": float(model.intercept_),
                "validation_abs_error_p95": float(np.quantile(np.abs(residuals), 0.95)),
            },
        }

    def forecast(
        self,
        time_series: list[dict[str, Any]],
        artifact: dict[str, Any],
        horizon_hours: int = 24,
    ) -> dict[str, Any]:
        df = pd.DataFrame(time_series)
        if df.empty:
            return {"status": "insufficient_data", "forecast": []}
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["timestamp", "value"])
        df = df[np.isfinite(df["value"])].drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
        if df.empty:
            return {"status": "insufficient_data", "forecast": []}

        gaps = df["timestamp"].diff().ne(pd.Timedelta(hours=1))
        df = df.loc[gaps.iloc[::-1].idxmax():].reset_index(drop=True)
        if len(df) < 24:
            return {
                "status": "insufficient_data",
                "reason": f"Se requieren 24 horas consecutivas para pronosticar; hay {len(df)}.",
                "forecast": [],
            }

        history = df["value"].astype(float).tolist()
        last_time = df["timestamp"].iloc[-1]
        coefficients = np.asarray(artifact["coefficients"], dtype=float)
        predictions = []
        error = max(0.0, float(artifact.get("validation_abs_error_p95", 0.0)))
        for hour in range(1, horizon_hours + 1):
            stamp = last_time + datetime.timedelta(hours=hour)
            features = np.array([
                stamp.hour,
                stamp.dayofweek,
                history[-1],
                history[-2],
                history[-24],
                float(np.mean(history[-6:])),
            ])
            prediction = max(0.0, float(np.dot(features, coefficients) + artifact["intercept"]))
            spread = error * math.sqrt(hour)
            predictions.append({
                "timestamp": stamp.isoformat(),
                "prediction": round(prediction, 2),
                "lower": round(max(0.0, prediction - spread), 2),
                "upper": round(prediction + spread, 2),
            })
            history.append(prediction)
        return {"status": "available", "forecast": predictions, "horizon_hours": horizon_hours}
