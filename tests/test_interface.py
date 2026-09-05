"""Offline UI acceptance checks. No API credits required."""
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services import solve_question
from test_services import FakeClient

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


class InterfaceTests(unittest.TestCase):
    def start(self):
        app = AppTest.from_file(str(APP), default_timeout=20)
        app.run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_public_configuration_fails_closed(self):
        app = self.start()
        solve = next(button for button in app.button if button.label == "Solve my question")
        self.assertTrue(solve.disabled)

    def test_examples_and_both_modes(self):
        app = self.start()
        next(button for button in app.button if button.label == "Algebra").click().run()
        self.assertIn("2x", app.text_area[0].value)
        app.radio[0].set_value("Multi-agent team").run()
        self.assertEqual(len(app.exception), 0)

    def test_research_and_about_navigation(self):
        app = self.start()
        app.sidebar.radio[0].set_value("Research").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.metric[0].value, "43.3%")
        app.sidebar.radio[0].set_value("About").run()
        self.assertEqual(len(app.exception), 0)

    def test_session_can_show_full_saved_result(self):
        app = self.start()
        app.session_state["history"] = [solve_question("2x+3=11", "single", FakeClient())]
        app.sidebar.radio[0].set_value("My session").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("Single Response" in item.label for item in app.expander))
