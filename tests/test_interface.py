"""Offline UI acceptance checks. No API credits required."""
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services import solve_question
from test_services import FakeClient

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


class InterfaceTests(unittest.TestCase):
    def test_uj_branding_and_student_identity(self):
        app = self.start()
        self.assertTrue(any('University of Johannesburg logo' in item.value for item in app.markdown))
        self.assertTrue(any('Student project by Hulisani Rambau' in item.value for item in app.markdown))
        self.assertFalse(any('not an official' in item.value.lower() for item in app.markdown))
        app.sidebar.radio[0].set_value('About').run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('student research prototype' in item.value for item in app.info))
        self.assertFalse(any('not an official' in item.value.lower() for item in app.info))

    def start(self):
        app = AppTest.from_file(str(APP), default_timeout=60)
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
        snapshot = json.loads((APP.parent / "research" / "snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(app.metric[0].value, f"{snapshot['overall']['single_accuracy']:.1%}")
        app.sidebar.radio[0].set_value("About").run()
        self.assertEqual(len(app.exception), 0)

    def test_session_can_show_full_saved_result(self):
        app = self.start()
        app.session_state["history"] = [solve_question("2x+3=11", "single", FakeClient())]
        app.sidebar.radio[0].set_value("My session").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("Single Response" in item.label for item in app.expander))

    def test_clear_editor_preserves_notebook(self):
        app = self.start()
        app.session_state["history"] = [solve_question("2x+3=11", "single", FakeClient())]
        next(button for button in app.button if button.label == "Algebra").click().run()
        next(button for button in app.button if button.label == "Clear question").click().run()
        self.assertEqual(app.text_area[0].value, "")
        self.assertEqual(len(app.session_state["history"]), 1)

    def test_notebook_clear_requires_confirmation(self):
        app = self.start()
        app.session_state["history"] = [solve_question("2x+3=11", "single", FakeClient())]
        app.sidebar.radio[0].set_value("My session").run()
        clear = next(button for button in app.button if button.label == "Clear my session history")
        self.assertTrue(clear.disabled)
        app.checkbox[0].check().run()
        next(button for button in app.button if button.label == "Clear my session history").click().run()
        self.assertEqual(app.session_state["history"], [])

    def test_solver_available_without_access_code(self):
        app = AppTest.from_file(str(APP), default_timeout=60)
        app.secrets["ZAI_API_KEY"] = "test-only-never-sent"
        app.secrets["APP_ACCESS_PASSWORD"] = "test-access"
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(any(item.label == "Presentation access code" for item in app.text_input))
        self.assertFalse(next(button for button in app.button if button.label == "Solve my question").disabled)

    def test_multi_solution_is_fully_accessible(self):
        app = self.start()
        app.session_state["answer"] = solve_question("2x+3=11", "multi", FakeClient())
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any(item.label == "Question answered" for item in app.expander))

    def test_expand_all_explanations(self):
        app = self.start()
        app.session_state['answer'] = solve_question('2x+3=11', 'multi', FakeClient())
        app.run()
        app.toggle[0].set_value(True).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('Independent verifier' in e.label for e in app.expander))
        self.assertTrue(app.session_state['expand_all_current'])

    def test_notebook_search_and_reopen_without_network(self):
        app = self.start()
        result = solve_question('2x+3=11', 'single', FakeClient())
        app.session_state['history'] = [result]
        with patch('services.CloudClient.generate', side_effect=AssertionError('Unexpected network call')):
            app.sidebar.radio[0].set_value('My session').run()
            app.text_input[0].set_value('no matching question').run()
            self.assertFalse(any(b.label == 'Use this question again' for b in app.button))
            app.text_input[0].set_value('2x').run()
            next(b for b in app.button if b.label == 'Use this question again').click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.sidebar.radio[0].value, 'Solve')
        self.assertEqual(app.text_area[0].value, result['problem'])
        self.assertEqual(len(app.session_state['history']), 1)

    def test_compare_saved_pair_without_provider_request(self):
        app = self.start()
        app.session_state['history'] = [solve_question('2x+3=11', mode, FakeClient()) for mode in ['single','multi']]
        with patch('services.CloudClient.generate', side_effect=AssertionError('Unexpected network call')):
            app.sidebar.radio[0].set_value('Compare').run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 4)

    def test_feedback_requires_consent_and_can_be_deleted(self):
        app = self.start()
        app.sidebar.radio[0].set_value('Feedback').run()
        next(b for b in app.button if b.label == 'Save feedback').click().run()
        self.assertEqual(app.session_state['feedback'], [])
        next(c for c in app.checkbox if 'agree' in c.label).check().run()
        next(b for b in app.button if b.label == 'Save feedback').click().run()
        self.assertEqual(len(app.session_state['feedback']), 1)
        next(b for b in app.button if b.label == 'Delete my feedback').click().run()
        self.assertEqual(app.session_state['feedback'], [])
