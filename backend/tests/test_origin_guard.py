"""Tests for common/origin_guard.py, which rejects requests that bypass the deployed CloudFront
distribution's shared-secret header."""
import unittest
from unittest.mock import patch

from src.common.origin_guard import is_trusted_origin


class IsTrustedOriginTest(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_no_secret_configured_allows_everything(self):
        # local_server.py / other unit tests never set ORIGIN_SECRET -- the guard must be a no-op
        # in that case, not silently reject every request.
        self.assertTrue(is_trusted_origin({}))
        self.assertTrue(is_trusted_origin({"headers": {}}))

    @patch.dict("os.environ", {"ORIGIN_SECRET": "s3cr3t"})
    def test_missing_header_is_rejected(self):
        self.assertFalse(is_trusted_origin({"headers": {}}))
        self.assertFalse(is_trusted_origin({}))

    @patch.dict("os.environ", {"ORIGIN_SECRET": "s3cr3t"})
    def test_wrong_header_value_is_rejected(self):
        event = {"headers": {"X-Pebble-Origin": "wrong"}}
        self.assertFalse(is_trusted_origin(event))

    @patch.dict("os.environ", {"ORIGIN_SECRET": "s3cr3t"})
    def test_correct_header_value_is_accepted(self):
        event = {"headers": {"X-Pebble-Origin": "s3cr3t"}}
        self.assertTrue(is_trusted_origin(event))

    @patch.dict("os.environ", {"ORIGIN_SECRET": "s3cr3t"})
    def test_header_lookup_is_case_insensitive(self):
        # API Gateway/CloudFront may deliver headers in any case.
        event = {"headers": {"x-pebble-origin": "s3cr3t"}}
        self.assertTrue(is_trusted_origin(event))


if __name__ == "__main__":
    unittest.main()
