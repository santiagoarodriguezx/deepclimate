"""
Spatial Anomaly Detection Engine.
Compares neighboring station observations across the Aburrá Valley.
Uses geodesic Haversine distance, neighborhood mean, standard deviation,
and local spatial z-deviation to detect localized sensor abnormalities or plumes.
"""

import math
from typing import List, Dict, Any


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two geographic coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class SpatialAnomalyDetector:
    def __init__(self, max_distance_km: float = 12.0, min_neighbors: int = 2, deviation_threshold: float = 2.2):
        self.max_distance_km = max_distance_km
        self.min_neighbors = min_neighbors
        self.deviation_threshold = deviation_threshold

    def detect_spatial_anomalies(
        self,
        station_observations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Takes a snapshot of latest station observations:
        [
          {
            "station_id": "ITA-CJUS",
            "station_name": "...",
            "municipality": "...",
            "latitude": 6.1856,
            "longitude": -75.5972,
            "value": 91.0,
            "variable_id": "PM25"
          }, ...
        ]
        Detects stations whose value deviates substantially from geographic neighbors.
        """
        station_observations = [
            row for row in station_observations
            if row.get("station_type") == "air_quality"
            and row.get("quality_status") not in {"unvalidated_unit", "retrieval_timestamp"}
        ]
        if len(station_observations) < 3:
            return []

        spatial_anomalies = []

        for i, target in enumerate(station_observations):
            t_lat = target["latitude"]
            t_lon = target["longitude"]
            t_val = target["value"]
            t_id = target["station_id"]

            neighbors = []
            for j, other in enumerate(station_observations):
                if i == j:
                    continue
                dist = haversine_distance_km(t_lat, t_lon, other["latitude"], other["longitude"])
                if dist <= self.max_distance_km:
                    neighbors.append({
                        "station_id": other["station_id"],
                        "station_name": other.get("station_name", other["station_id"]),
                        "distance_km": round(dist, 2),
                        "value": other["value"]
                    })

            # Sort by distance
            neighbors.sort(key=lambda x: x["distance_km"])
            k_neighbors = neighbors[:6]

            if len(k_neighbors) < self.min_neighbors:
                continue

            neighbor_vals = [n["value"] for n in k_neighbors]
            neighbor_mean = sum(neighbor_vals) / len(neighbor_vals)
            neighbor_var = sum((v - neighbor_mean) ** 2 for v in neighbor_vals) / len(neighbor_vals)
            neighbor_std = math.sqrt(neighbor_var) if neighbor_var > 0 else 1.0

            local_deviation = (t_val - neighbor_mean) / max(neighbor_std, 2.0)

            # Check if target strongly deviates from local group
            if abs(local_deviation) >= self.deviation_threshold and abs(t_val - neighbor_mean) >= 10.0:
                spatial_anomalies.append({
                    "station_id": t_id,
                    "station_name": target.get("station_name", t_id),
                    "municipality": target.get("municipality", "Medellín"),
                    "value": round(t_val, 2),
                    "neighbor_mean": round(neighbor_mean, 2),
                    "neighbor_std": round(neighbor_std, 2),
                    "local_deviation_score": round(local_deviation, 2),
                    "difference": round(t_val - neighbor_mean, 2),
                    "direction": "higher_than_neighbors" if t_val > neighbor_mean else "lower_than_neighbors",
                    "neighbor_count": len(k_neighbors),
                    "closest_neighbors": [
                        {
                            "station_id": n["station_id"],
                            "station_name": n["station_name"],
                            "distance_km": n["distance_km"],
                            "value": round(n["value"], 2)
                        }
                        for n in k_neighbors[:3]
                    ]
                })

        return spatial_anomalies
