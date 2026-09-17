"""Covers src/context/schema.py and src/context/prompt.py in isolation from Bedrock's
retry/timeout/fallback plumbing (see test_context.py for that layer)."""
import json
import unittest
from pathlib import Path

from src.context.prompt import CONTEXT_SYSTEM_PROMPT, build_context_prompt
from src.context.schema import CONTEXT_TOOL_NAME, validate_context_tool_output

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "context_fixtures.json"


class ContextFixtureSchemaTest(unittest.TestCase):
    """Fixtures are the spec (CONTEXT_PIPELINE_PLAN.md Track D) -- every fixture response must
    validate against the Bedrock tool-use schema the live Lambda will enforce."""

    def test_every_fixture_response_validates_against_tool_schema(self):
        fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(fixtures), 3)
        for fixture in fixtures:
            error = validate_context_tool_output(fixture["response"])
            self.assertIsNone(error, f"fixture {fixture['description']!r}: {error}")

    def test_safety_and_addressed_question_fixtures_flag_and_aside_does_not(self):
        fixtures = {f["description"]: f["response"] for f in json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))}
        safety = next(v for k, v in fixtures.items() if "safety" in k)
        addressed = next(v for k, v in fixtures.items() if "addressed" in k)
        aside = next(v for k, v in fixtures.items() if "aside" in k)

        self.assertTrue(safety["flaggedMoment"]["present"])
        self.assertIn("STOP", safety["flaggedMoment"]["icons"])
        self.assertTrue(addressed["flaggedMoment"]["present"])
        self.assertFalse(aside["flaggedMoment"]["present"])
        self.assertEqual(aside["flaggedMoment"]["label"], "")
        self.assertEqual(aside["flaggedMoment"]["icons"], [])


class ContextToolOutputValidationTest(unittest.TestCase):
    VALID = {
        "summary": "The group is building a tower.",
        "dynamicIcons": [{"word": "tower"}, {"word": "block"}],
        "flaggedMoment": {"present": False, "label": "", "icons": []},
    }

    def test_valid_output_passes(self):
        self.assertIsNone(validate_context_tool_output(self.VALID))

    def test_present_true_requires_nonempty_label_and_icons(self):
        candidate = {
            **self.VALID,
            "flaggedMoment": {"present": True, "label": "", "icons": []},
        }
        self.assertIsNotNone(validate_context_tool_output(candidate))

    def test_present_false_rejects_nonempty_label_or_icons(self):
        candidate = {
            **self.VALID,
            "flaggedMoment": {"present": False, "label": "not actually empty", "icons": []},
        }
        self.assertIsNotNone(validate_context_tool_output(candidate))

    def test_more_than_six_dynamic_icons_rejected(self):
        candidate = {**self.VALID, "dynamicIcons": [{"word": f"w{i}"} for i in range(7)]}
        self.assertIsNotNone(validate_context_tool_output(candidate))

    def test_duplicate_dynamic_icon_words_rejected(self):
        candidate = {**self.VALID, "dynamicIcons": [{"word": "tower"}, {"word": "Tower"}]}
        self.assertIsNotNone(validate_context_tool_output(candidate))

    def test_unknown_icon_id_rejected(self):
        candidate = {
            **self.VALID,
            "flaggedMoment": {"present": True, "label": "hi", "icons": ["NOT_A_REAL_ICON"]},
        }
        self.assertIsNotNone(validate_context_tool_output(candidate))

    def test_extra_top_level_key_rejected(self):
        candidate = {**self.VALID, "confidence": 0.9}
        self.assertIsNotNone(validate_context_tool_output(candidate))


class ContextPromptTest(unittest.TestCase):
    def test_prompt_delimits_inputs_as_data(self):
        raw_window = [{"text": "connect the wire", "timestamp": 1000}]
        prompt = build_context_prompt("prior summary", raw_window, "circuits lab")
        serialized = prompt.split("<context_update_request>", 1)[1].split(
            "</context_update_request>", 1
        )[0]
        data = json.loads(serialized)

        self.assertEqual(data["summary"], "prior summary")
        self.assertEqual(data["rawWindow"], raw_window)
        self.assertEqual(data["activityAnchor"], "circuits lab")

    def test_system_prompt_states_never_guess_and_forces_tool_call(self):
        self.assertIn("never guess", CONTEXT_SYSTEM_PROMPT.lower())
        self.assertIn(CONTEXT_TOOL_NAME, CONTEXT_SYSTEM_PROMPT)
        self.assertIn("STOP", CONTEXT_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
