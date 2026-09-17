"""Tests for common/dynamo.py's GET/PUT profile logic directly (the DynamoDB-facing layer), plus
request-body validation for POST /profile/{id}. Success/404/502 status-code shaping through the
Lambda handler is covered by ProfileLiveWiringTest in test_live_wiring.py, which mocks
get_profile/put_profile at the app layer -- this file instead exercises common/dynamo.py's own
fallback, TTL-expiry, and malformed-item handling by mocking the DynamoDB table itself."""
import json
import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from botocore.exceptions import BotoCoreError, ClientError

from src.common.dynamo import FIXTURE_PATH, get_profile, put_profile
from src.profile.app import lambda_handler as profile_handler


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "GetItem")


def _fixture_profile(profile_id):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return fixture["profiles"][profile_id]["profile"]


def _valid_item(**overrides):
    item = {
        "profileId": "demo",
        "vocabLevel": "advanced",
        "sentenceLength": "long",
        "tone": "playful",
        "interests": ["dinosaurs"],
        "expiresAt": Decimal(int(time.time()) + 3600),
    }
    item.update(overrides)
    return item


class GetProfileTest(unittest.TestCase):
    @patch("src.common.dynamo.get_table")
    def test_hit_returns_exactly_four_contract_fields(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": _valid_item()}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "live")
        self.assertEqual(
            profile,
            {
                "vocabLevel": "advanced",
                "sentenceLength": "long",
                "tone": "playful",
                "interests": ["dinosaurs"],
            },
        )
        mock_table.get_item.assert_called_once_with(Key={"profileId": "demo"}, ConsistentRead=True)

    @patch("src.common.dynamo.get_table")
    def test_miss_falls_back_to_fixture_profile(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))

    @patch("src.common.dynamo.get_table")
    def test_client_error_falls_back_to_fixture_profile(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.side_effect = _client_error("ProvisionedThroughputExceededException")
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo_alt")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo_alt"))

    @patch("src.common.dynamo.get_table")
    def test_botocore_error_falls_back_to_fixture_profile(self, mock_get_table):
        # BotoCoreError (missing credentials, connection failures) is a distinct exception family
        # from ClientError (AWS-side API errors) -- both must degrade the same way, never crash.
        mock_table = MagicMock()
        mock_table.get_item.side_effect = BotoCoreError()
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))

    @patch("src.common.dynamo.get_table")
    def test_unknown_profile_id_with_no_saved_item_returns_none(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("nobody")

        self.assertIsNone(profile)
        self.assertEqual(source, "fallback")

    @patch("src.common.dynamo.get_table")
    def test_expired_item_treated_as_miss(self, mock_get_table):
        # DynamoDB's TTL deletion is a background sweep that can lag well past the timestamp -- a
        # still-present-but-expired item must not be trusted just because get_item returned it.
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": _valid_item(expiresAt=Decimal(int(time.time()) - 10))
        }
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))

    @patch("src.common.dynamo.get_table")
    def test_item_missing_required_field_treated_as_miss(self, mock_get_table):
        item = _valid_item()
        del item["sentenceLength"]
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": item}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))

    @patch("src.common.dynamo.get_table")
    def test_item_with_wrong_typed_field_treated_as_miss(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": _valid_item(interests="dinosaurs")}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))

    @patch("src.common.dynamo.get_table")
    def test_whitespace_only_field_treated_as_miss(self, mock_get_table):
        # _extract_traits reuses validate_profile_request (the same validator POST runs), which
        # rejects whitespace-only strings via .strip() -- a naive `not value` check alone would
        # have let this through, since a non-empty whitespace string is truthy.
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": _valid_item(tone="   ")}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))

    @patch("src.common.dynamo.get_table")
    def test_empty_interests_list_treated_as_miss(self, mock_get_table):
        # all(...) over an empty list is vacuously True, so a per-item non-empty-string check alone
        # would have let an empty interests list through -- validate_profile_request explicitly
        # requires a non-empty array.
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": _valid_item(interests=[])}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))

    @patch("src.common.dynamo.get_table")
    def test_oversized_field_treated_as_miss(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": _valid_item(vocabLevel="x" * 101)}
        mock_get_table.return_value = mock_table

        profile, source = get_profile("demo")

        self.assertEqual(source, "fallback")
        self.assertEqual(profile, _fixture_profile("demo"))


class PutProfileTest(unittest.TestCase):
    VALID_PROFILE = {
        "vocabLevel": "simple",
        "sentenceLength": "short",
        "tone": "direct",
        "interests": ["blocks"],
    }

    @patch("src.common.dynamo.get_table")
    def test_success_returns_true_and_writes_expires_at(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        result = put_profile("demo", self.VALID_PROFILE)

        self.assertTrue(result)
        item = mock_table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["profileId"], "demo")
        self.assertIn("expiresAt", item)
        self.assertGreater(item["expiresAt"], int(time.time()))

    @patch("src.common.dynamo.get_table")
    def test_client_error_returns_false(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.put_item.side_effect = _client_error("ProvisionedThroughputExceededException")
        mock_get_table.return_value = mock_table

        self.assertFalse(put_profile("demo", self.VALID_PROFILE))

    @patch("src.common.dynamo.get_table")
    def test_botocore_error_returns_false(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.put_item.side_effect = BotoCoreError()
        mock_get_table.return_value = mock_table

        self.assertFalse(put_profile("demo", self.VALID_PROFILE))


class ProfileRequestValidationTest(unittest.TestCase):
    """POST body validation happens before any DynamoDB call, so these run through the real
    lambda_handler with no mocking needed."""

    def _event(self, body):
        return {"httpMethod": "POST", "pathParameters": {"id": "demo"}, "body": json.dumps(body)}

    def test_missing_field_returns_400(self):
        result = profile_handler(self._event({"vocabLevel": "simple"}), None)
        self.assertEqual(result["statusCode"], 400)

    def test_unexpected_extra_key_returns_400(self):
        # An accidental/unexpected extra key (e.g. a stray "studentName") must be rejected outright,
        # never silently stored or echoed back as if it were part of the frozen 4-field contract.
        body = {
            "vocabLevel": "simple", "sentenceLength": "short", "tone": "direct",
            "interests": ["blocks"], "studentName": "Maya",
        }
        result = profile_handler(self._event(body), None)
        self.assertEqual(result["statusCode"], 400)

    def test_empty_string_field_returns_400(self):
        body = {"vocabLevel": "", "sentenceLength": "short", "tone": "direct", "interests": ["blocks"]}
        result = profile_handler(self._event(body), None)
        self.assertEqual(result["statusCode"], 400)

    def test_wrong_typed_field_returns_400(self):
        body = {"vocabLevel": 5, "sentenceLength": "short", "tone": "direct", "interests": ["blocks"]}
        result = profile_handler(self._event(body), None)
        self.assertEqual(result["statusCode"], 400)

    def test_oversized_field_returns_400(self):
        body = {"vocabLevel": "x" * 101, "sentenceLength": "short", "tone": "direct", "interests": ["blocks"]}
        result = profile_handler(self._event(body), None)
        self.assertEqual(result["statusCode"], 400)

    def test_too_many_interests_returns_400(self):
        body = {
            "vocabLevel": "simple", "sentenceLength": "short", "tone": "direct",
            "interests": [f"interest-{i}" for i in range(11)],
        }
        result = profile_handler(self._event(body), None)
        self.assertEqual(result["statusCode"], 400)

    def test_oversized_interest_returns_400(self):
        body = {
            "vocabLevel": "simple", "sentenceLength": "short", "tone": "direct",
            "interests": ["x" * 51],
        }
        result = profile_handler(self._event(body), None)
        self.assertEqual(result["statusCode"], 400)

    def test_missing_path_id_returns_400(self):
        event = {"httpMethod": "GET", "pathParameters": {}, "body": None}
        result = profile_handler(event, None)
        self.assertEqual(result["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
