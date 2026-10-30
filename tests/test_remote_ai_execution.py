import datetime as dt
import json
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.llm import NvidiaNimAssistant
from backend.agent.jev import JevAgent
from backend.database.models import Base, SourceRun


class RemoteAiExecutionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_successful_remote_call_is_logged_and_public_metadata_redacts_text(self):
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "La señal observada es parcial."}}]}
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.post.return_value = response
        assistant = NvidiaNimAssistant()
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-only", "NVIDIA_MODEL": "nvidia/test-model"}), patch("backend.agent.llm.httpx.Client", return_value=client):
            answer, model = assistant.explain("¿Cómo está el PM2.5?", {"PM25": 12.3})
        self.assertEqual(answer, "La señal observada es parcial.")
        self.assertEqual(model, "nvidia/test-model")
        self.assertEqual(assistant.last_execution["status"], "success")
        self.assertIn("input", assistant.last_execution)
        self.assertEqual(assistant.last_execution["output"], answer)

        agent = JevAgent(self.db)
        agent._persist_remote_execution("nvidia_nim", assistant.last_execution)
        run = self.db.query(SourceRun).one()
        stored = json.loads(run.metadata_json)
        public = run.to_dict()
        self.assertEqual(run.status, "success")
        self.assertGreaterEqual(run.latency_ms, 0)
        self.assertEqual(stored["output"], answer)
        self.assertNotIn("input", public["metadata"])
        self.assertNotIn("output", public["metadata"])
        self.assertGreater(public["metadata"]["input_chars"], 0)

    def test_remote_error_is_recorded_as_failed_execution(self):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.post.side_effect = TimeoutError("provider timeout")
        assistant = NvidiaNimAssistant()
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-only", "NVIDIA_MODEL": "nvidia/test-model"}), patch("backend.agent.llm.httpx.Client", return_value=client):
            with self.assertRaises(TimeoutError):
                assistant.explain("consulta", {"verified": True})
        self.assertEqual(assistant.last_execution["status"], "failed")
        self.assertIn("TimeoutError", assistant.last_execution["error"])
        agent = JevAgent(self.db)
        agent._persist_remote_execution("nvidia_nim", assistant.last_execution)
        run = self.db.query(SourceRun).one()
        self.assertEqual(run.status, "failed")
        self.assertIn("TimeoutError", run.error_message)


if __name__ == "__main__":
    unittest.main()
