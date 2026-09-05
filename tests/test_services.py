import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import CloudClient, RequestGate, SolverError, retry_delay, solve_question


class FakeClient:
    model = "test-model"
    provider_name = "test-provider"
    def generate(self, role, prompt, context=None):
        return "Subtract 3, then divide by 2. FINAL ANSWER: 4"


class ServiceTests(unittest.TestCase):
    def test_empty_question_is_rejected(self):
        with self.assertRaises(SolverError):
            solve_question(" ", "single", FakeClient())

    def test_length_limit(self):
        with self.assertRaises(SolverError):
            solve_question("x" * 4001, "single", FakeClient())

    def test_invalid_mode(self):
        with self.assertRaises(SolverError):
            solve_question("2+2", "crewai", FakeClient())

    def test_single_export_has_provenance(self):
        result = solve_question("2x+3=11", "single", FakeClient())
        self.assertEqual(result["final_answer"], "4")
        self.assertEqual(result["model"], "test-model")
        self.assertIn("single_v2", result["architecture_version"])

    def test_team_consensus(self):
        result = solve_question("2x+3=11", "multi", FakeClient())
        self.assertEqual(result["verdict"], "CONSENSUS")
        self.assertEqual(result["final_answer"], "4")

    def test_failure_does_not_become_a_fake_answer(self):
        client = FakeClient()
        client.generate = lambda **kwargs: (_ for _ in ()).throw(SolverError("provider unavailable"))
        with self.assertRaises(SolverError):
            solve_question("2+2", "single", client)

    def test_key_not_in_repr(self):
        self.assertNotIn("private-test-key", repr(CloudClient("private-test-key")))

    def test_retry_after_is_respected(self):
        self.assertEqual(retry_delay("120", 0), 120)
        self.assertEqual(retry_delay("invalid", 1), 10)

    def test_request_ceiling(self):
        gate = RequestGate(daily_limit=1)
        gate.reserve()
        with self.assertRaises(SolverError):
            gate.reserve()

    def test_long_cooldown_is_actionable(self):
        gate = RequestGate()
        gate.cooldown(120)
        with self.assertRaisesRegex(SolverError, "cooling down"):
            gate.reserve()


if __name__ == "__main__":
    unittest.main()
