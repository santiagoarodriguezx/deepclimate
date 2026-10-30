"""
Station Clustering Engine.
Groups stations according to environmental behavior, pollution dynamics,
diurnal cycles, and altitude into distinct functional clusters:
- Grupo 1: Corredor urbano de tráfico y alta densidad
- Grupo 2: Zonas residenciales e intermedias del valle
- Grupo 3: Estaciones periféricas y de alta elevación
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any
from sklearn.cluster import KMeans


class StationClusterEngine:
    CLUSTER_LABELS = {
        0: "Concentración relativa más alta",
        1: "Concentración relativa intermedia",
        2: "Concentración relativa más baja"
    }

    CLUSTER_DESCRIPTIONS = {
        0: "Agrupación exploratoria por la lectura PM2.5 disponible; no identifica causas ni fuentes de emisión.",
        1: "Agrupación exploratoria por la lectura PM2.5 disponible; no identifica causas ni fuentes de emisión.",
        2: "Agrupación exploratoria por la lectura PM2.5 disponible; no identifica causas ni fuentes de emisión."
    }

    def __init__(self, n_clusters: int = 3):
        self.n_clusters = n_clusters

    def cluster_stations(
        self,
        station_feature_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Takes station features:
        [
          {
            "station_id": "MED-PJIC",
            "station_name": "...",
            "municipality": "Medellín",
            "mean_pm25": 24.5,
            "std_pm25": 9.2,
            "p95_pm25": 42.0,
            "morning_peak_ratio": 1.45,
            "latitude": 6.208,
            "longitude": -75.577
          }, ...
        ]
        """
        if not station_feature_list:
            return {
                "status": "insufficient_data",
                "n_clusters": 0,
                "clusters": [],
            }

        df = pd.DataFrame(station_feature_list)
        df["current_pm25"] = pd.to_numeric(df["current_pm25"], errors="coerce")
        df = df.dropna(subset=["current_pm25"])
        n_c = min(self.n_clusters, len(df), df["current_pm25"].nunique())
        if n_c == 0:
            return {"status": "insufficient_data", "n_clusters": 0, "clusters": []}
        df["cluster_id"] = KMeans(n_clusters=n_c, random_state=42, n_init=10).fit_predict(df[["current_pm25"]].values)

        # Order clusters by mean PM2.5 so cluster 0 is always highest / traffic
        means = df.groupby("cluster_id")["current_pm25"].mean().sort_values(ascending=False)
        mapping = {old: new for new, old in enumerate(means.index)}
        df["cluster_id"] = df["cluster_id"].map(mapping)

        clusters_result = []
        for c_id in sorted(df["cluster_id"].unique()):
            sub = df[df["cluster_id"] == c_id]
            stations_in_cluster = sub[["station_id", "station_name", "municipality", "current_pm25"]].rename(
                columns={"current_pm25": "pm25"}
            ).to_dict(orient="records")

            clusters_result.append({
                "cluster_id": int(c_id),
                "label": "Lecturas similares" if n_c == 1 else self.CLUSTER_LABELS.get(c_id, f"Grupo {c_id + 1}"),
                "description": self.CLUSTER_DESCRIPTIONS.get(c_id, ""),
                "station_count": len(sub),
                "avg_pm25": round(float(sub["current_pm25"].mean()), 2),
                "stations": stations_in_cluster
            })

        return {
            "status": "available",
            "n_clusters": len(clusters_result),
            "clusters": clusters_result
        }
