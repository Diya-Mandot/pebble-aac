import json
import unittest

from src.expand.app import lambda_handler as expand_handler
from src.simplify.app import lambda_handler as simplify_handler
from src.common.icons import ICON_IDS, QUICK_REPLY_IDS


class ExpandContractTest(unittest.TestCase):
    def test_candidates_use_valid_icon_derived_shape(self):
        event = {
            "body": json.dumps(
                {"icons": ["CONFUSED", "BUILD", "HELP"], "context": "", "profileId": "demo"}
            )
        }
        result = expand_handler(event, None)
        self.assertEqual(result["statusCode"], 200)

        body = json.loads(result["body"])
        self.assertEqual(body["source"], "mock")
        self.assertIn("candidates", body)
        self.assertGreater(len(body["candidates"]), 0)
        for candidate in body["candidates"]:
            self.assertIn("id", candidate)
            self.assertIn("text", candidate)
            self.assertIsInstance(candidate["text"], str)

    def test_profiles_produce_different_candidates_for_same_request(self):
        request = {
            "icons": ["CONFUSED", "BUILD", "HELP"],
            "context": "classroom group project",
        }
        results = []
        for profile_id in ("demo", "demo_alt"):
            result = expand_handler(
                {"body": json.dumps({**request, "profileId": profile_id})}, None
            )
            self.assertEqual(result["statusCode"], 200)
            results.append(json.loads(result["body"])["candidates"])

        self.assertNotEqual(results[0], results[1])

    def test_unknown_profile_uses_documented_default_fixture(self):
        request = {"icons": ["CONFUSED", "BUILD", "HELP"], "context": ""}
        default_result = expand_handler(
            {"body": json.dumps({**request, "profileId": "demo"})}, None
        )
        unknown_result = expand_handler(
            {"body": json.dumps({**request, "profileId": "not-yet-loaded"})}, None
        )
        self.assertEqual(
            json.loads(default_result["body"])["candidates"],
            json.loads(unknown_result["body"])["candidates"],
        )

    def test_unknown_icon_id_returns_400(self):
        event = {
            "body": json.dumps(
                {"icons": ["NOT_A_REAL_ICON"], "context": "", "profileId": "demo"}
            )
        }
        result = expand_handler(event, None)
        self.assertEqual(result["statusCode"], 400)

    def test_non_string_icon_returns_400(self):
        event = {
            "body": json.dumps({"icons": [{}], "context": "", "profileId": "demo"})
        }
        result = expand_handler(event, None)
        self.assertEqual(result["statusCode"], 400)

    def test_missing_context_returns_400(self):
        event = {
            "body": json.dumps({"icons": ["CONFUSED"], "profileId": "demo"})
        }
        result = expand_handler(event, None)
        self.assertEqual(result["statusCode"], 400)


class SimplifyContractTest(unittest.TestCase):
    def test_wiring_negation_fixture_includes_stop_check_warning(self):
        # PLAN.md test fixtures: this exact line must yield a STOP/CHECK warning for "switch off".
        event = {
            "body": json.dumps(
                {
                    "text": (
                        "take the red wire, connect it to the battery first, "
                        "but make sure the switch is off"
                    )
                }
            )
        }
        result = simplify_handler(event, None)
        self.assertEqual(result["statusCode"], 200)

        body = json.loads(result["body"])
        self.assertEqual(body["source"], "mock")
        self.assertEqual(body["status"], "ok")

        warning_icons = {icon for warning in body["warnings"] for icon in warning["icons"]}
        self.assertIn("STOP", warning_icons)
        self.assertIn("CHECK", warning_icons)

        for reply in body["quickReplies"]:
            self.assertIn(reply, QUICK_REPLY_IDS)
        for step in body["steps"]:
            for icon in step["icons"]:
                self.assertIn(icon, ICON_IDS)

    def test_empty_text_returns_400(self):
        result = simplify_handler({"body": json.dumps({"text": ""})}, None)
        self.assertEqual(result["statusCode"], 400)

    def test_unmatched_input_returns_labeled_please_repeat_with_verbatim_transcript(self):
        submitted = "the quick brown fox jumps over the lazy dog"
        result = simplify_handler({"body": json.dumps({"text": submitted})}, None)
        self.assertEqual(result["statusCode"], 200)

        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["status"], "please_repeat")
        self.assertEqual(body["steps"], [])
        self.assertEqual(body["warnings"], [])
        self.assertEqual(body["quickReplies"], ["NEED_HELP"])
        # Transcript must be verbatim — never a canned/fabricated line.
        self.assertEqual(body["transcript"], submitted)


if __name__ == "__main__":
    unittest.main()
