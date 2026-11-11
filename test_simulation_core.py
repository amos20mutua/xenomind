import json
import tempfile
import unittest
from pathlib import Path

from simulation_core import (
    REQUIRED_RECORD_FIELDS,
    SANDBOX_HEIGHT,
    SANDBOX_WIDTH,
    SCENARIOS,
    ScenarioEngine,
    append_event,
)


class ScenarioEngineTests(unittest.TestCase):
    def test_seed_reproduces_scenario_sequence(self) -> None:
        first = ScenarioEngine("First Contact", seed=123)
        second = ScenarioEngine("First Contact", seed=123)

        first_events = [first.next_event("session", index) for index in range(12)]
        second_events = [second.next_event("session", index) for index in range(12)]

        self.assertEqual(
            [(event.event_type, event.application, event.details) for event in first_events],
            [(event.event_type, event.application, event.details) for event in second_events],
        )

    def test_all_scenario_actions_are_confined_to_sandbox(self) -> None:
        for scenario_name in SCENARIOS:
            engine = ScenarioEngine(scenario_name, seed=7)
            for sequence in range(100):
                event = engine.next_event("session", sequence)
                record = event.to_record()
                self.assertTrue(record["synthetic"])
                self.assertEqual(record["scope"], "in_app_sandbox")
                self.assertFalse(record["real_input_sent"])
                self.assertEqual(record["session_id"], "session")
                if event.surface_x is not None:
                    self.assertLessEqual(event.surface_x, SANDBOX_WIDTH - 16)
                    self.assertGreaterEqual(event.surface_x, 16)
                    self.assertLessEqual(event.surface_y, SANDBOX_HEIGHT - 16)
                    self.assertGreaterEqual(event.surface_y, 16)
                else:
                    self.assertIsNone(event.surface_y)

    def test_unknown_scenario_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ScenarioEngine("unrecognized", seed=1)

    def test_event_record_includes_the_complete_synthetic_schema(self) -> None:
        event = ScenarioEngine("Dream Sequence", seed=2).next_event("session", 0)
        record = event.to_record()

        self.assertTrue(REQUIRED_RECORD_FIELDS.issubset(record))
        self.assertTrue(record["synthetic"])
        self.assertEqual(record["scope"], "in_app_sandbox")
        self.assertFalse(record["real_input_sent"])

    def test_append_event_writes_one_synthetic_json_line(self) -> None:
        event = ScenarioEngine("Dream Sequence", seed=2).next_event("session", 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "events.jsonl"
            output.write_text('{"existing":true}\n', encoding="utf-8")
            append_event(output, event)
            lines = output.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), {"existing": True})
        record = json.loads(lines[1])
        self.assertTrue(record["synthetic"])
        self.assertFalse(record["real_input_sent"])
        self.assertEqual(record["scope"], "in_app_sandbox")

    def test_append_event_creates_parent_directories_for_string_paths(self) -> None:
        event = ScenarioEngine("Signal Migration", seed=4).next_event("session", 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "logs" / "events.jsonl"
            append_event(str(output), event)
            self.assertTrue(output.exists())
            self.assertTrue(output.parent.exists())
            self.assertTrue(json.loads(output.read_text(encoding="utf-8").strip())["synthetic"])


if __name__ == "__main__":
    unittest.main()
