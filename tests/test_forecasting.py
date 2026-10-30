import datetime
import unittest

from backend.ml.forecasting.predictor import EnvironmentalForecaster


class EnvironmentalForecasterTests(unittest.TestCase):
    def setUp(self):
        self.forecaster = EnvironmentalForecaster()
        self.start = datetime.datetime(2026, 1, 1)

    def series(self, count):
        return [
            {
                "timestamp": (self.start + datetime.timedelta(hours=i)).isoformat(),
                "value": 12 + i % 24 * 0.2,
            }
            for i in range(count)
        ]

    def test_training_is_temporal_and_returns_baseline_metrics(self):
        result = self.forecaster.train(self.series(120))

        self.assertEqual(result["status"], "trained")
        self.assertGreater(result["validation_points"], 0)
        self.assertIn("baseline_mae", result["metrics"])
        self.assertEqual(result["training_points"], 96)

    def test_forecast_requires_a_contiguous_recent_history(self):
        artifact = {
            "coefficients": [0, 0, 0, 0, 0, 0],
            "intercept": 5,
            "validation_abs_error_p95": 2,
        }
        points = self.series(30) + [
            {
                "timestamp": (self.start + datetime.timedelta(hours=40 + i)).isoformat(),
                "value": 14,
            }
            for i in range(23)
        ]

        result = self.forecaster.forecast(points, artifact, horizon_hours=6)

        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["forecast"], [])

    def test_forecast_emits_bounded_intervals(self):
        trained = self.forecaster.train(self.series(120))
        result = self.forecaster.forecast(self.series(120), trained["artifact"], horizon_hours=6)

        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["forecast"]), 6)
        self.assertTrue(all(p["lower"] <= p["prediction"] <= p["upper"] for p in result["forecast"]))


if __name__ == "__main__":
    unittest.main()
