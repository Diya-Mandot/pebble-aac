"""Covers expand/app.py and simplify/app.py's response shaping around invoke_expand/invoke_simplify
in isolation from Bedrock's retry/timeout/fallback plumbing (see test_contract.py for that layer,
and test_expand_prompt.py for the /expand prompt+schema module).
"""
import json
import unittest
from unittest.mock import patch

from src.expand.app import lambda_handler as expand_handler
from src.simplify.app import lambda_handler as simplify_handler
from src.speak.app import lambda_handler as speak_handler


EXPAND_EVENT = {
    "body": json.dumps(
        {"icons": ["CONFUSED", "BUILD", "HELP"], "context": "classroom group project", "profileId": "demo"}
    )
}
SIMPLIFY_EVENT = {"body": json.dumps({"text": "put the block on the table"})}
SPEAK_EVENT = {"body": json.dumps({"text": "I'm done"})}


class ExpandLiveWiringTest(unittest.TestCase):
    @patch("src.expand.app.invoke_expand")
    def test_valid_bedrock_response_is_labeled_live(self, mock_invoke):
        live_candidates = [
            {"id": "c1", "text": "One"},
            {"id": "c2", "text": "Two"},
            {"id": "c3", "text": "Three"},
        ]
        mock_invoke.return_value = (live_candidates, "live")

        result = expand_handler(EXPAND_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["candidates"], live_candidates)

    @patch("src.expand.app.invoke_expand")
    def test_failed_bedrock_call_falls_back_to_fixture_labeled_fallback(self, mock_invoke):
        fallback_candidates = [
            {"id": "c1", "text": "Fallback one"},
            {"id": "c2", "text": "Fallback two"},
            {"id": "c3", "text": "Fallback three"},
        ]
        mock_invoke.return_value = (fallback_candidates, "fallback")

        result = expand_handler(EXPAND_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertGreater(len(body["candidates"]), 0)


class SimplifyLiveWiringTest(unittest.TestCase):
    @patch("src.simplify.app.invoke_simplify")
    def test_valid_bedrock_response_is_labeled_live_with_verbatim_transcript(self, mock_invoke):
        mock_invoke.return_value = (
            {
                "status": "ok",
                "steps": [{"icons": ["BUILD"], "label": "Put the block on the table"}],
                "warnings": [],
                "quickReplies": ["DONE", "NEED_HELP"],
            },
            "live",
        )

        result = simplify_handler(SIMPLIFY_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["transcript"], "put the block on the table")

    @patch("src.simplify.app.invoke_simplify")
    def test_failed_bedrock_call_falls_back_to_labeled_please_repeat(self, mock_invoke):
        mock_invoke.return_value = (
            {
                "status": "please_repeat",
                "steps": [],
                "warnings": [],
                "quickReplies": ["NEED_HELP"],
            },
            "fallback",
        )

        result = simplify_handler(SIMPLIFY_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["status"], "please_repeat")
        self.assertEqual(body["steps"], [])
        self.assertEqual(body["warnings"], [])
        # Transcript must stay verbatim even on the live-call fallback path.
        self.assertEqual(body["transcript"], "put the block on the table")


class SpeakLiveWiringTest(unittest.TestCase):
    @patch("src.speak.app.invoke_speak")
    def test_valid_response_is_labeled_live(self, mock_invoke):
        mock_invoke.return_value = ("ZmFrZS1hdWRpbw==", "live")

        result = speak_handler(SPEAK_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["contentType"], "audio/mpeg")
        self.assertEqual(body["audioBase64"], "ZmFrZS1hdWRpbw==")

    @patch("src.speak.app.invoke_speak")
    def test_failed_call_with_no_safe_fallback_returns_no_audio(self, mock_invoke):
        # invoke_speak returns (None, "fallback") when the requested text doesn't match the one
        # bundled recorded clip -- app.py must surface that as "no audio", never substitute
        # anything, per the P1 fix (see common/polly.py's module docstring).
        mock_invoke.return_value = (None, "fallback")

        result = speak_handler(SPEAK_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertIsNone(body["audioBase64"])
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()
