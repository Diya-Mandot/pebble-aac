"""Covers the live-Bedrock branch of Track C's wiring that the mock-path fixtures in
test_contract.py can't exercise, since BEDROCK_MODEL_ID/AWS_REGION are still TODO
placeholders in this environment (PLAN.md "Next 60 minutes" item 5, blocked on AWS
account access). Mocks common.bedrock.invoke_tool so the live/fallback branches in
expand/app.py and simplify/app.py run without a real AWS call, so this must be
re-verified against a real `converse` call once Bedrock access is confirmed.
"""
import json
import unittest
from unittest.mock import patch

from src.expand.app import lambda_handler as expand_handler
from src.simplify.app import lambda_handler as simplify_handler


EXPAND_EVENT = {
    "body": json.dumps(
        {"icons": ["CONFUSED", "BUILD", "HELP"], "context": "classroom group project", "profileId": "demo"}
    )
}
SIMPLIFY_EVENT = {"body": json.dumps({"text": "put the block on the table"})}


class ExpandLiveWiringTest(unittest.TestCase):
    @patch("src.expand.app.bedrock_configured", return_value=True)
    @patch("src.expand.app.invoke_tool")
    def test_valid_bedrock_response_is_labeled_live(self, mock_invoke, _mock_configured):
        live_candidates = {
            "candidates": [
                {"id": "c1", "text": "One"},
                {"id": "c2", "text": "Two"},
                {"id": "c3", "text": "Three"},
            ]
        }
        mock_invoke.return_value = (live_candidates, None)

        result = expand_handler(EXPAND_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["candidates"], live_candidates["candidates"])

    @patch("src.expand.app.bedrock_configured", return_value=True)
    @patch("src.expand.app.invoke_tool")
    def test_failed_bedrock_call_falls_back_to_fixture_labeled_fallback(
        self, mock_invoke, _mock_configured
    ):
        mock_invoke.return_value = (None, "invalid tool output twice")

        result = expand_handler(EXPAND_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertGreater(len(body["candidates"]), 0)


class SimplifyLiveWiringTest(unittest.TestCase):
    @patch("src.simplify.app.bedrock_configured", return_value=True)
    @patch("src.simplify.app.invoke_tool")
    def test_valid_bedrock_response_is_labeled_live_with_verbatim_transcript(
        self, mock_invoke, _mock_configured
    ):
        mock_invoke.return_value = (
            {
                "status": "ok",
                "steps": [{"icons": ["BUILD"], "label": "Put the block on the table"}],
                "warnings": [],
                "quickReplies": ["DONE", "NEED_HELP"],
            },
            None,
        )

        result = simplify_handler(SIMPLIFY_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["transcript"], "put the block on the table")

    @patch("src.simplify.app.bedrock_configured", return_value=True)
    @patch("src.simplify.app.invoke_tool")
    def test_failed_bedrock_call_falls_back_to_labeled_please_repeat(
        self, mock_invoke, _mock_configured
    ):
        mock_invoke.return_value = (None, "invalid tool output twice")

        result = simplify_handler(SIMPLIFY_EVENT, None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["status"], "please_repeat")
        self.assertEqual(body["steps"], [])
        self.assertEqual(body["warnings"], [])
        # Transcript must stay verbatim even on the live-call fallback path.
        self.assertEqual(body["transcript"], "put the block on the table")


if __name__ == "__main__":
    unittest.main()
