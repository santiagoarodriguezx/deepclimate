import datetime
import os
import unittest
from unittest.mock import Mock, patch

from backend.agent.llm import NvidiaNimAssistant, OpenRouterAssistant, configured_assistant
from backend.ml.correlations.engine import CorrelationEngine


class AnalyticsTests(unittest.TestCase):
    def test_correlation_reports_missing_data_without_fake_zero_metrics(self):
        result = CorrelationEngine().calculate_correlation(
            [{"timestamp": "2026-01-01T00:00:00", "value": 1.0}],
            [],
            name_a="rain",
            name_b="PM25",
        )

        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["pearson"])
        self.assertEqual(result["aligned_points"], 0)

    def test_openrouter_skips_call_without_credentials(self):
        assistant = OpenRouterAssistant()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(assistant.explain("pregunta", {}), (None, None))

    def test_nvidia_is_preferred_when_both_remote_keys_are_configured(self):
        with patch.dict(os.environ, {
            "NVIDIA_API_KEY": "nvidia-test-key",
            "OPENROUTER_API_KEY": "openrouter-test-key",
            "OPENROUTER_MODEL": "some/model",
        }, clear=True):
            assistant, provider = configured_assistant()
        self.assertIsInstance(assistant, NvidiaNimAssistant)
        self.assertEqual(provider, "nvidia_nim")

    def test_nvidia_explanation_uses_hosted_api_and_never_needs_local_model(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Resumen verificado."}}]}
        client = Mock()
        client.post.return_value = response
        client_context = Mock()
        client_context.__enter__ = Mock(return_value=client)
        client_context.__exit__ = Mock(return_value=None)
        NvidiaNimAssistant._request_times.clear()
        try:
            with patch.dict(os.environ, {"NVIDIA_API_KEY": "nvidia-test-key"}, clear=True), \
                    patch("backend.agent.llm.httpx.Client", return_value=client_context):
                answer = NvidiaNimAssistant().explain("¿Qué muestran los datos?", {"rain_mm": 3})
        finally:
            NvidiaNimAssistant._request_times.clear()

        self.assertEqual(answer, ("Resumen verificado.", "nvidia/nemotron-3.5-bolt-e4b"))
        client.post.assert_called_once()
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer nvidia-test-key")
        self.assertEqual(kwargs["json"]["model"], "nvidia/nemotron-3.5-bolt-e4b")
        self.assertIn("No calcules ni sustituyas pronósticos", kwargs["json"]["messages"][0]["content"])

    def test_openrouter_sliding_rate_limit(self):
        OpenRouterAssistant._request_times.clear()
        try:
            self.assertTrue(all(OpenRouterAssistant._allow_request() for _ in range(10)))
            self.assertFalse(OpenRouterAssistant._allow_request())
        finally:
            OpenRouterAssistant._request_times.clear()


if __name__ == "__main__":
    unittest.main()
