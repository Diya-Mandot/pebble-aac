import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from src.common.validation import validate_expand_candidates, validate_expand_output
from src.expand.prompt import (
    EXPAND_OUTPUT_SCHEMA,
    EXPAND_SYSTEM_PROMPT,
    EXPAND_TOOL_CONFIG,
    EXPAND_TOOL_NAME,
    build_expand_prompt,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "expand_default.json"


class ExpandPromptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_schema_and_all_reviewed_fixture_outputs_are_valid(self):
        Draft202012Validator.check_schema(EXPAND_OUTPUT_SCHEMA)
        for fixture_profile in self.fixture["profiles"].values():
            self.assertIsNone(validate_expand_output(fixture_profile["response"]))

    def test_tool_config_forces_schema_constrained_expand_tool(self):
        tool_spec = EXPAND_TOOL_CONFIG["tools"][0]["toolSpec"]
        self.assertEqual(tool_spec["name"], EXPAND_TOOL_NAME)
        self.assertIs(tool_spec["inputSchema"]["json"], EXPAND_OUTPUT_SCHEMA)
        self.assertEqual(
            EXPAND_TOOL_CONFIG["toolChoice"], {"tool": {"name": EXPAND_TOOL_NAME}}
        )

    def test_schema_rejects_wrong_counts_missing_and_additional_fields(self):
        valid_candidates = [
            {"id": "c1", "text": "One"},
            {"id": "c2", "text": "Two"},
            {"id": "c3", "text": "Three"},
        ]
        invalid_outputs = [
            {"candidates": valid_candidates[:2]},
            {"candidates": valid_candidates + [{"id": "c4", "text": "Four"}]},
            {"candidates": [{"id": "c1"}, *valid_candidates[1:]]},
            {"candidates": [{"id": "c1", "text": "", "extra": True}, *valid_candidates[1:]]},
            {"candidates": valid_candidates, "source": "live"},
        ]
        for output in invalid_outputs:
            with self.subTest(output=output):
                self.assertIsNotNone(validate_expand_output(output))

    def test_validator_rejects_duplicate_candidate_ids(self):
        output = {
            "candidates": [
                {"id": "same", "text": "One"},
                {"id": "same", "text": "Two"},
                {"id": "other", "text": "Three"},
            ]
        }
        self.assertEqual(validate_expand_output(output), "Candidate ids must be unique")

    def test_profile_fixture_text_is_reviewed_and_contains_no_added_specifics(self):
        expected = {
            "demo": [
                "I'm confused about building this. Can you help?",
                "I don't understand this part. Please help me build it.",
                "How do I build this? I need help.",
            ],
            "demo_alt": [
                "I'm not sure how to build this. Could we work through it together?",
                "This build is confusing me. Can someone explain how to approach it?",
                "I need some help understanding how this goes together.",
            ],
        }
        actual = {
            profile_id: [item["text"] for item in data["response"]["candidates"]]
            for profile_id, data in self.fixture["profiles"].items()
        }
        self.assertEqual(actual, expected)
        self.assertNotEqual(actual["demo"], actual["demo_alt"])

        unsupported_specifics = re.compile(
            r"\b(?:monday|tuesday|wednesday|thursday|friday|tomorrow|yesterday|"
            r"promise|promised|will meet|must finish|teacher|mom|dad|john|jane|\d+)\b",
            re.IGNORECASE,
        )
        for candidates in actual.values():
            for text in candidates:
                self.assertIsNone(unsupported_specifics.search(text))

    def test_prompt_delimits_inputs_and_limits_personalization(self):
        profile = self.fixture["profiles"]["demo_alt"]["profile"]
        tokens = [{"kind": "icon", "id": icon} for icon in self.fixture["request"]["icons"]]
        prompt = build_expand_prompt(tokens, self.fixture["request"]["context"], profile)
        serialized = prompt.split("<expansion_request>", 1)[1].split(
            "</expansion_request>", 1
        )[0]
        prompt_data = json.loads(serialized)

        self.assertEqual(prompt_data["tokens"], tokens)
        self.assertEqual(prompt_data["context"], "classroom group project")
        self.assertEqual(prompt_data["profile"], profile)
        self.assertIn("untrusted data", prompt)
        self.assertIn("never add content from the profile", prompt)
        self.assertIn("Interests may shape word", EXPAND_SYSTEM_PROMPT)
        self.assertIn("must never add content or facts", EXPAND_SYSTEM_PROMPT)

    def test_prompt_describes_word_tokens_and_ordering(self):
        self.assertIn("word", EXPAND_SYSTEM_PROMPT)
        self.assertIn("given order", EXPAND_SYSTEM_PROMPT)
        self.assertIn("verbatim", EXPAND_SYSTEM_PROMPT)

    def test_tokens_serialize_with_ordered_kind_and_payload(self):
        tokens = [{"kind": "word", "word": "battery"}, {"kind": "icon", "id": "HELP"}]
        prompt = build_expand_prompt(tokens, "", {})
        serialized = prompt.split("<expansion_request>", 1)[1].split(
            "</expansion_request>", 1
        )[0]
        self.assertEqual(json.loads(serialized)["tokens"], tokens)


class ValidateExpandCandidatesWordTest(unittest.TestCase):
    VALID = [
        {"id": "c1", "text": "I want the battery."},
        {"id": "c2", "text": "Can I have the battery?"},
        {"id": "c3", "text": "Battery, please."},
    ]

    def test_rejects_candidates_omitting_a_selected_word(self):
        missing = [
            {"id": "c1", "text": "I want to say something."},
            {"id": "c2", "text": "Can we talk about this?"},
            {"id": "c3", "text": "I'm trying to communicate."},
        ]
        self.assertIsNotNone(validate_expand_candidates(missing, ["battery"]))

    def test_accepts_case_insensitive_word_boundary_match(self):
        self.assertIsNone(validate_expand_candidates(self.VALID, ["battery"]))

    def test_rejects_partial_word_match(self):
        candidates = [
            {"id": "c1", "text": "I have two batteries."},
            {"id": "c2", "text": "The batteries are dead."},
            {"id": "c3", "text": "Batteries, please."},
        ]
        self.assertIsNotNone(validate_expand_candidates(candidates, ["battery"]))

    def test_no_words_required_is_unaffected(self):
        self.assertIsNone(validate_expand_candidates(self.VALID, []))


if __name__ == "__main__":
    unittest.main()
