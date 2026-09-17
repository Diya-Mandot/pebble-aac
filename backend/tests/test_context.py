"""Covers POST /context/update end to end: request validation, live/fallback response shaping,
retry/timeout plumbing, and the scripted-vs-generic fallback split. Mirrors test_contract.py's
ExpandContractTest/SimplifyContractTest structure for the ambient context pipeline's backend
endpoint (CONTEXT_PIPELINE_PLAN.md Track D)."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from src.context.app import lambda_handler as context_handler
from src.context.schema import CONTEXT_TOOL_NAME
from src.common.bedrock import MIN_MS_FOR_ATTEMPT, _transform_context_tool_output

CONTEXT_FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "context_fixtures.json"


def _tool_use_response(input_dict, tool_name=CONTEXT_TOOL_NAME):
    return {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "t1", "name": tool_name, "input": input_dict}}
                ],
            }
        },
    }


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "Converse")


NO_FLAG = {"present": False, "label": "", "icons": []}

VALID_RAW_OUTPUT = {
    "summary": "The group is building a tower.",
    "dynamicIcons": [{"word": "tower", "symbol": "building"}, {"word": "block", "symbol": "none"}],
    "flaggedMoment": NO_FLAG,
}

# Missing an unrelated required top-level field.
MALFORMED_RAW_OUTPUT = {"summary": "The group is building a tower.", "flaggedMoment": NO_FLAG}


class ContextRequestValidationTest(unittest.TestCase):
    def _event(self, **overrides):
        body = {
            "summary": "",
            "rawWindow": [{"text": "connect the wire", "timestamp": 1000}],
            "activityAnchor": "circuits lab",
        }
        body.update(overrides)
        return {"body": json.dumps(body)}

    def test_missing_summary_returns_400(self):
        body = json.loads(self._event()["body"])
        del body["summary"]
        result = context_handler({"body": json.dumps(body)}, None)
        self.assertEqual(result["statusCode"], 400)

    def test_empty_raw_window_returns_400(self):
        result = context_handler(self._event(rawWindow=[]), None)
        self.assertEqual(result["statusCode"], 400)

    def test_raw_window_item_missing_timestamp_returns_400(self):
        result = context_handler(self._event(rawWindow=[{"text": "hi"}]), None)
        self.assertEqual(result["statusCode"], 400)

    def test_raw_window_item_non_string_text_returns_400(self):
        result = context_handler(self._event(rawWindow=[{"text": 5, "timestamp": 1}]), None)
        self.assertEqual(result["statusCode"], 400)

    def test_too_many_raw_window_turns_returns_400(self):
        turns = [{"text": f"turn {i}", "timestamp": i} for i in range(9)]
        result = context_handler(self._event(rawWindow=turns), None)
        self.assertEqual(result["statusCode"], 400)

    def test_non_string_activity_anchor_returns_400(self):
        result = context_handler(self._event(activityAnchor=5), None)
        self.assertEqual(result["statusCode"], 400)

    def test_empty_body_returns_400(self):
        result = context_handler({"body": None}, None)
        self.assertEqual(result["statusCode"], 400)


class ContextContractTest(unittest.TestCase):
    def _event(self, raw_window, activity_anchor="", summary=""):
        return {
            "body": json.dumps(
                {"summary": summary, "rawWindow": raw_window, "activityAnchor": activity_anchor}
            )
        }

    @patch("src.common.bedrock.get_client")
    def test_valid_bedrock_response_is_labeled_live_and_omits_flagged_moment(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.return_value = _tool_use_response(VALID_RAW_OUTPUT)
        mock_get_client.return_value = mock_client

        result = context_handler(
            self._event([{"text": "we are building a tower", "timestamp": 1}]), None
        )
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["summary"], "The group is building a tower.")
        self.assertEqual(body["dynamicIcons"], [{"word": "tower", "symbol": "building"}, {"word": "block"}])
        self.assertNotIn("flaggedMoment", body)

    @patch("src.common.bedrock.get_client")
    def test_flagged_moment_present_is_included_in_response(self, mock_get_client):
        raw = {
            "summary": "A peer warned the student not to touch a hot part.",
            "dynamicIcons": [{"word": "hot", "symbol": "flame"}],
            "flaggedMoment": {"present": True, "label": "Don't touch, it's hot", "icons": ["STOP", "CHECK"]},
        }
        mock_client = MagicMock()
        mock_client.converse.return_value = _tool_use_response(raw)
        mock_get_client.return_value = mock_client

        result = context_handler(
            self._event([{"text": "don't touch that, it's hot", "timestamp": 1}]), None
        )
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "live")
        self.assertEqual(body["flaggedMoment"], {"label": "Don't touch, it's hot", "icons": ["STOP", "CHECK"]})

    @patch("src.common.bedrock.get_client")
    def test_falls_back_to_scripted_fixture_for_exact_wiring_safety_transcript(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        fixtures = json.loads(CONTEXT_FIXTURES_PATH.read_text(encoding="utf-8"))
        fixture = next(f for f in fixtures if "safety" in f["description"])
        request = fixture["request"]

        result = context_handler(
            self._event(request["rawWindow"], request["activityAnchor"], request["summary"]), None
        )
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        self.assertIn("flaggedMoment", body)
        self.assertIn("STOP", body["flaggedMoment"]["icons"])
        expected = _transform_context_tool_output(fixture["response"])["dynamicIcons"]
        self.assertEqual(body["dynamicIcons"], expected)

    @patch("src.common.bedrock.get_client")
    def test_falls_back_to_generic_deterministic_response_for_unscripted_transcript(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        result = context_handler(
            self._event(
                [{"text": "we should paint the birdhouse yellow tomorrow", "timestamp": 1}],
                activity_anchor="art class",
                summary="prior summary text",
            ),
            None,
        )
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["summary"], "prior summary text")
        self.assertNotIn("flaggedMoment", body)
        words = {icon["word"].lower() for icon in body["dynamicIcons"]}
        self.assertTrue({"paint", "birdhouse", "yellow", "tomorrow"} & words)
        self.assertTrue(all("symbol" not in icon for icon in body["dynamicIcons"]))

    @patch("src.common.bedrock.get_client")
    def test_retries_once_on_malformed_output_then_succeeds(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            _tool_use_response(MALFORMED_RAW_OUTPUT),
            _tool_use_response(VALID_RAW_OUTPUT),
        ]
        mock_get_client.return_value = mock_client

        result = context_handler(self._event([{"text": "building a tower", "timestamp": 1}]), None)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "live")
        self.assertEqual(mock_client.converse.call_count, 2)

    @patch("src.common.bedrock.get_client")
    def test_unknown_symbol_in_raw_output_is_rejected_then_falls_back(self, mock_get_client):
        bad_symbol_output = {
            "summary": "The group is building a tower.",
            "dynamicIcons": [{"word": "tower", "symbol": "not-a-real-symbol"}],
            "flaggedMoment": NO_FLAG,
        }
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            _tool_use_response(bad_symbol_output),
            _tool_use_response(bad_symbol_output),
        ]
        mock_get_client.return_value = mock_client

        result = context_handler(self._event([{"text": "building a tower", "timestamp": 1}]), None)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        self.assertEqual(mock_client.converse.call_count, 2)

    @patch("src.common.bedrock.get_client")
    def test_does_not_retry_permanent_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("AccessDeniedException")
        mock_get_client.return_value = mock_client

        result = context_handler(self._event([{"text": "building a tower", "timestamp": 1}]), None)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        self.assertEqual(mock_client.converse.call_count, 1)

    @patch("src.common.bedrock.get_client")
    def test_skips_bedrock_call_when_insufficient_lambda_time_remains(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        context = MagicMock()
        context.get_remaining_time_in_millis.return_value = MIN_MS_FOR_ATTEMPT - 1

        result = context_handler(self._event([{"text": "building a tower", "timestamp": 1}]), context)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        mock_client.converse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
