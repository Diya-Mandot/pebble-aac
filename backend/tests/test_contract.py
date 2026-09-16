import json
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from src.expand.app import lambda_handler as expand_handler
from src.simplify.app import lambda_handler as simplify_handler
from src.common.bedrock import FIXTURES_PATH, MIN_MS_FOR_ATTEMPT
from src.common.icons import ICON_IDS, QUICK_REPLY_IDS


def _tool_use_response(candidates, tool_name="provide_candidates"):
    return {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "t1",
                            "name": tool_name,
                            "input": {"candidates": candidates},
                        }
                    }
                ],
            }
        },
    }


VALID_CANDIDATES = [
    {"id": "c1", "text": "I'm confused about how to build this."},
    {"id": "c2", "text": "I don't understand this part of the build."},
    {"id": "c3", "text": "Something about the build is confusing me."},
]

MALFORMED_RESPONSE = _tool_use_response([{"id": "c1", "text": "only one candidate"}])


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "Converse")


def _simplify_tool_use_response(response_dict, tool_name="provide_simplification"):
    return {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "t1",
                            "name": tool_name,
                            "input": response_dict,
                        }
                    }
                ],
            }
        },
    }


WIRING_TEXT = (
    "take the red wire, connect it to the battery first, but make sure the switch is off"
)

VALID_SIMPLIFY_RESPONSE = {
    "status": "ok",
    "steps": [
        {"icons": ["IDEA", "BUILD"], "label": "Take the red wire"},
        {"icons": ["BUILD"], "label": "Connect it to the battery first"},
    ],
    "warnings": [
        {"icons": ["STOP", "CHECK"], "label": "Make sure the switch is off"},
    ],
    "quickReplies": ["DONE", "NEED_HELP"],
}

# "ok" with zero steps/warnings is invalid per validate_simplify_response -- a no-op success.
MALFORMED_SIMPLIFY_RESPONSE = _simplify_tool_use_response(
    {"status": "ok", "steps": [], "warnings": [], "quickReplies": ["DONE"]}
)

# An extra top-level key must be rejected even though the tool schema already forbids it -- the
# Lambda validator can't just trust Bedrock to have honored additionalProperties: false.
EXTRA_KEY_SIMPLIFY_RESPONSE = _simplify_tool_use_response(
    {**VALID_SIMPLIFY_RESPONSE, "confidence": 0.9}
)

# A pure-warning message ("Stop!") with zero steps must still validate as a successful "ok".
WARNINGS_ONLY_SIMPLIFY_RESPONSE = {
    "status": "ok",
    "steps": [],
    "warnings": [{"icons": ["STOP"], "label": "Stop!"}],
    "quickReplies": ["DONE", "NEED_HELP"],
}


class ExpandContractTest(unittest.TestCase):
    def _event(self, icons=("CONFUSED", "BUILD", "HELP"), context=""):
        return {
            "body": json.dumps(
                {"icons": list(icons), "context": context, "profileId": "demo"}
            )
        }

    def _assert_valid_shape(self, body):
        self.assertIn("candidates", body)
        self.assertEqual(len(body["candidates"]), 3)
        for candidate in body["candidates"]:
            self.assertIn("id", candidate)
            self.assertIn("text", candidate)
            self.assertIsInstance(candidate["text"], str)

    @patch("src.common.bedrock.get_client")
    def test_candidates_use_valid_icon_derived_shape(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.return_value = _tool_use_response(VALID_CANDIDATES)
        mock_get_client.return_value = mock_client

        result = expand_handler(self._event(), None)
        self.assertEqual(result["statusCode"], 200)

        body = json.loads(result["body"])
        self.assertEqual(body["source"], "live")
        self._assert_valid_shape(body)

    @patch("src.common.bedrock.get_client")
    def test_falls_back_to_scripted_fixture_after_exhausting_retries(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        result = expand_handler(self._event(), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self._assert_valid_shape(body)
        # The scripted fixture (not the mocked live model's candidates) must come back verbatim.
        scripted = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))[0]["response"]["candidates"]
        self.assertEqual(body["candidates"], scripted)

    @patch("src.common.bedrock.get_client")
    def test_falls_back_to_deterministic_response_for_unscripted_icons(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        result = expand_handler(self._event(icons=("AGREE", "DONE")), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self._assert_valid_shape(body)
        for candidate in body["candidates"]:
            self.assertIn("agree, done", candidate["text"].lower())

    @patch("src.common.bedrock.get_client")
    def test_retries_once_on_malformed_output_then_succeeds(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            MALFORMED_RESPONSE,
            _tool_use_response(VALID_CANDIDATES),
        ]
        mock_get_client.return_value = mock_client

        result = expand_handler(self._event(), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "live")
        self.assertEqual(mock_client.converse.call_count, 2)

    @patch("src.common.bedrock.get_client")
    def test_does_not_retry_permanent_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("AccessDeniedException")
        mock_get_client.return_value = mock_client

        result = expand_handler(self._event(), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(mock_client.converse.call_count, 1)

    @patch("src.common.bedrock.get_client")
    def test_skips_bedrock_call_when_insufficient_lambda_time_remains(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        context = MagicMock()
        context.get_remaining_time_in_millis.return_value = MIN_MS_FOR_ATTEMPT - 1

        result = expand_handler(self._event(), context)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        mock_client.converse.assert_not_called()

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
    def _event(self, text):
        return {"body": json.dumps({"text": text})}

    def _assert_stop_check_warning(self, body):
        warning_icons = {icon for warning in body["warnings"] for icon in warning["icons"]}
        self.assertIn("STOP", warning_icons)
        self.assertIn("CHECK", warning_icons)
        for reply in body["quickReplies"]:
            self.assertIn(reply, QUICK_REPLY_IDS)
        for step in body["steps"]:
            for icon in step["icons"]:
                self.assertIn(icon, ICON_IDS)

    @patch("src.common.bedrock.get_client")
    def test_wiring_negation_live_includes_stop_check_warning(self, mock_get_client):
        # PLAN.md test fixtures: this exact line must yield a STOP/CHECK warning for "switch off".
        mock_client = MagicMock()
        mock_client.converse.return_value = _simplify_tool_use_response(VALID_SIMPLIFY_RESPONSE)
        mock_get_client.return_value = mock_client

        result = simplify_handler(self._event(WIRING_TEXT), None)
        self.assertEqual(result["statusCode"], 200)

        body = json.loads(result["body"])
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["transcript"], WIRING_TEXT)
        self._assert_stop_check_warning(body)

    @patch("src.common.bedrock.get_client")
    def test_falls_back_to_scripted_fixture_for_wiring_text(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        result = simplify_handler(self._event(WIRING_TEXT), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["transcript"], WIRING_TEXT)
        self._assert_stop_check_warning(body)

    @patch("src.common.bedrock.get_client")
    def test_falls_back_to_please_repeat_for_unmatched_text_on_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        submitted = "the quick brown fox jumps over the lazy dog"
        result = simplify_handler(self._event(submitted), None)

        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["status"], "please_repeat")
        self.assertEqual(body["steps"], [])
        self.assertEqual(body["warnings"], [])
        self.assertEqual(body["quickReplies"], ["NEED_HELP"])
        # Transcript must be verbatim — never a canned/fabricated line, even on failure.
        self.assertEqual(body["transcript"], submitted)

    @patch("src.common.bedrock.get_client")
    def test_retries_once_on_malformed_output_then_succeeds(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            MALFORMED_SIMPLIFY_RESPONSE,
            _simplify_tool_use_response(VALID_SIMPLIFY_RESPONSE),
        ]
        mock_get_client.return_value = mock_client

        result = simplify_handler(self._event(WIRING_TEXT), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "live")
        self.assertEqual(mock_client.converse.call_count, 2)

    @patch("src.common.bedrock.get_client")
    def test_does_not_retry_permanent_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.converse.side_effect = _client_error("AccessDeniedException")
        mock_get_client.return_value = mock_client

        result = simplify_handler(self._event(WIRING_TEXT), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(mock_client.converse.call_count, 1)

    def test_empty_text_returns_400(self):
        result = simplify_handler({"body": json.dumps({"text": ""})}, None)
        self.assertEqual(result["statusCode"], 400)

    @patch("src.common.bedrock.get_client")
    def test_rejects_extra_top_level_key_and_falls_back(self, mock_get_client):
        # The tool schema already forbids this (additionalProperties: false), but the Lambda
        # validator must independently reject it rather than trust Bedrock to have honored that.
        mock_client = MagicMock()
        mock_client.converse.return_value = EXTRA_KEY_SIMPLIFY_RESPONSE
        mock_get_client.return_value = mock_client

        result = simplify_handler(self._event(WIRING_TEXT), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(mock_client.converse.call_count, 2)

    @patch("src.common.bedrock.get_client")
    def test_warnings_only_response_is_valid_ok(self, mock_get_client):
        # A pure-warning message ("Stop!") with zero steps is a valid "ok" response on its own.
        mock_client = MagicMock()
        mock_client.converse.return_value = _simplify_tool_use_response(
            WARNINGS_ONLY_SIMPLIFY_RESPONSE
        )
        mock_get_client.return_value = mock_client

        result = simplify_handler(self._event("Stop!"), None)
        body = json.loads(result["body"])
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["steps"], [])
        self.assertEqual(body["warnings"], [{"icons": ["STOP"], "label": "Stop!"}])


if __name__ == "__main__":
    unittest.main()
