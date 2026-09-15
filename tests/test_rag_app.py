"""Streamlit interaction tests; run in the isolated App environment."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_rag_service import fake_clients

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

APP = Path(__file__).resolve().parents[1] / "apps/rag_chat/app.py"


@unittest.skipIf(AppTest is None, "Install apps/rag_chat/requirements.txt to test the UI")
class RagAppTest(unittest.TestCase):
    def test_answer_feedback_export_and_session_isolation(self):
        index, chat = fake_clients()
        with patch("src.analytics_ai.rag_clients.create_clients", return_value=(index, chat)):
            app = AppTest.from_file(str(APP)).run()
            self.assertFalse(app.exception)
            app.chat_input[0].set_value("Como funciona a ingestão?").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.expander), 1)
            app.radio[0].set_value("Útil").run()
            self.assertFalse(app.exception)
            record = app.session_state["interactions"][0]
            self.assertEqual(record.feedback, "useful")
            from src.analytics_ai.rag_service import export_interactions
            self.assertEqual(json.loads(export_interactions([record]))["interactions"][0]["feedback"], "useful")
            self.assertEqual(len(app.get("download_button")), 1)
            chat.create.assert_called_once()
            index.similarity_search.assert_called_once()
            other = AppTest.from_file(str(APP)).run()
            self.assertEqual(other.session_state["interactions"], [])

    def test_refusal_without_credentials(self):
        with patch("src.analytics_ai.rag_clients.create_clients") as factory:
            app = AppTest.from_file(str(APP)).run()
            app.chat_input[0].set_value("Qual o faturamento atual?").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["interactions"][0].status, "refused")
            factory.assert_not_called()

    def test_empty_context_and_error_are_distinct(self):
        index, chat = fake_clients()
        index.similarity_search.return_value = {"result": {"data_array": []}}
        with patch("src.analytics_ai.rag_clients.create_clients", return_value=(index, chat)):
            app = AppTest.from_file(str(APP)).run()
            app.chat_input[0].set_value("Como funciona?").run()
            self.assertFalse(app.exception)
            self.assertTrue(app.info)
            index.similarity_search.side_effect = RuntimeError("secret-test-value")
            app.chat_input[0].set_value("Como funciona agora?").run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertNotIn("secret-test-value", app.error[0].value)
            chat.create.assert_not_called()
