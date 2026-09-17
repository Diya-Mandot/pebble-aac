import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

import src.common.polly as polly_module
from src.common.polly import FALLBACK_AUDIO_PATH, FALLBACK_METADATA_PATH, MIN_MS_FOR_ATTEMPT
from src.common.polly import _call_once, _load_fallback
from src.speak.app import lambda_handler as speak_handler


FALLBACK_TEXT = "I'm confused about building this. Can you help?"
UNMATCHED_TEXT = "I'm done"


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "SynthesizeSpeech")


def _mock_stream(read_return=b"fake-mp3-bytes", read_side_effect=None):
    stream = MagicMock()
    if read_side_effect is not None:
        stream.read.side_effect = read_side_effect
    else:
        stream.read.return_value = read_return
    return stream


def _synthesize_response(content_type="audio/mpeg", stream=None):
    return {
        "AudioStream": _mock_stream() if stream is None else stream,
        "ContentType": content_type,
    }


class SpeakContractTest(unittest.TestCase):
    def _event(self, text):
        return {"body": json.dumps({"text": text})}

    @patch("src.common.polly.get_client")
    def test_live_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = _synthesize_response()
        mock_get_client.return_value = mock_client

        result = speak_handler(self._event("anything approved"), None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "live")
        self.assertEqual(body["contentType"], "audio/mpeg")
        self.assertEqual(base64.b64decode(body["audioBase64"]), b"fake-mp3-bytes")

    @patch("src.common.polly.get_client")
    def test_retries_once_on_transient_error_then_succeeds(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.synthesize_speech.side_effect = [
            _client_error("ThrottlingException"),
            _synthesize_response(),
        ]
        mock_get_client.return_value = mock_client

        result = speak_handler(self._event("anything approved"), None)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "live")
        self.assertEqual(mock_client.synthesize_speech.call_count, 2)

    @patch("src.common.polly._load_fallback")
    @patch("src.common.polly.get_client")
    def test_does_not_retry_permanent_error(self, mock_get_client, mock_load_fallback):
        mock_load_fallback.return_value = ("ZmFrZQ==", FALLBACK_TEXT)
        mock_client = MagicMock()
        mock_client.synthesize_speech.side_effect = _client_error("AccessDeniedException")
        mock_get_client.return_value = mock_client

        result = speak_handler(self._event(UNMATCHED_TEXT), None)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        self.assertEqual(mock_client.synthesize_speech.call_count, 1)

    @patch("src.common.polly._load_fallback")
    @patch("src.common.polly.get_client")
    def test_falls_back_to_bundled_clip_when_text_matches(self, mock_get_client, mock_load_fallback):
        mock_load_fallback.return_value = ("ZmFrZS1mYWxsYmFjaw==", FALLBACK_TEXT)
        mock_client = MagicMock()
        mock_client.synthesize_speech.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        result = speak_handler(self._event(FALLBACK_TEXT), None)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["audioBase64"], "ZmFrZS1mYWxsYmFjaw==")
        self.assertNotIn("error", body)

    @patch("src.common.polly._load_fallback")
    @patch("src.common.polly.get_client")
    def test_falls_back_to_no_audio_when_text_does_not_match_bundled_clip(
        self, mock_get_client, mock_load_fallback
    ):
        # P1 regression: the bundled clip may ONLY be played back for the exact sentence it was
        # recorded for. Playing it for anything else would speak words the student never approved.
        mock_load_fallback.return_value = ("ZmFrZS1mYWxsYmFjaw==", FALLBACK_TEXT)
        mock_client = MagicMock()
        mock_client.synthesize_speech.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        result = speak_handler(self._event(UNMATCHED_TEXT), None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertIsNone(body["audioBase64"])
        self.assertNotEqual(body.get("audioBase64"), "ZmFrZS1mYWxsYmFjaw==")
        self.assertIn("error", body)

    @patch("src.common.polly._load_fallback")
    @patch("src.common.polly.get_client")
    def test_falls_back_to_no_audio_when_fallback_asset_missing_or_unreadable(
        self, mock_get_client, mock_load_fallback
    ):
        # _load_fallback() returns (None, None) when speak_fallback.mp3/.json haven't been
        # generated yet or are corrupt -- must degrade to "no audio" like a text mismatch, never
        # crash the request (PLAN.md: "every AWS call has a hard fallback").
        mock_load_fallback.return_value = (None, None)
        mock_client = MagicMock()
        mock_client.synthesize_speech.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        result = speak_handler(self._event(FALLBACK_TEXT), None)
        body = json.loads(result["body"])

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertIsNone(body["audioBase64"])
        self.assertIn("error", body)

    @patch("src.common.polly._load_fallback")
    @patch("src.common.polly.get_client")
    def test_skips_call_when_insufficient_lambda_time_remains(
        self, mock_get_client, mock_load_fallback
    ):
        mock_load_fallback.return_value = ("ZmFrZQ==", FALLBACK_TEXT)
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        context = MagicMock()
        context.get_remaining_time_in_millis.return_value = MIN_MS_FOR_ATTEMPT - 1

        result = speak_handler(self._event(FALLBACK_TEXT), context)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        mock_client.synthesize_speech.assert_not_called()

    def test_empty_text_returns_400(self):
        result = speak_handler(self._event(""), None)
        self.assertEqual(result["statusCode"], 400)

    def test_missing_text_key_returns_400(self):
        result = speak_handler({"body": json.dumps({})}, None)
        self.assertEqual(result["statusCode"], 400)

    def test_text_exceeding_max_length_returns_400(self):
        result = speak_handler(self._event("x" * 501), None)
        self.assertEqual(result["statusCode"], 400)


class CallOnceStreamHandlingTest(unittest.TestCase):
    """Unit tests against common.polly._call_once directly: a malformed Polly response must never
    be labeled "live", and the AudioStream must be closed on every exit path so a warm Lambda
    invocation doesn't leak the underlying HTTP connection."""

    @patch("src.common.polly.get_client")
    def test_missing_audio_stream_raises(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = {"ContentType": "audio/mpeg"}
        mock_get_client.return_value = mock_client

        with self.assertRaises(ValueError):
            _call_once("hello")

    @patch("src.common.polly.get_client")
    def test_wrong_content_type_raises_and_closes_stream(self, mock_get_client):
        stream = _mock_stream()
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = _synthesize_response(
            content_type="text/plain", stream=stream
        )
        mock_get_client.return_value = mock_client

        with self.assertRaises(ValueError):
            _call_once("hello")
        stream.close.assert_called_once()

    @patch("src.common.polly.get_client")
    def test_empty_audio_raises_and_closes_stream(self, mock_get_client):
        stream = _mock_stream(read_return=b"")
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = _synthesize_response(stream=stream)
        mock_get_client.return_value = mock_client

        with self.assertRaises(ValueError):
            _call_once("hello")
        stream.close.assert_called_once()

    @patch("src.common.polly.get_client")
    def test_read_exception_propagates_and_closes_stream(self, mock_get_client):
        stream = _mock_stream(read_side_effect=OSError("boom"))
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = _synthesize_response(stream=stream)
        mock_get_client.return_value = mock_client

        with self.assertRaises(OSError):
            _call_once("hello")
        stream.close.assert_called_once()

    @patch("src.common.polly.get_client")
    def test_valid_response_returns_bytes_and_closes_stream(self, mock_get_client):
        stream = _mock_stream(read_return=b"fake-mp3-bytes")
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = _synthesize_response(stream=stream)
        mock_get_client.return_value = mock_client

        audio_bytes = _call_once("hello")

        self.assertEqual(audio_bytes, b"fake-mp3-bytes")
        stream.close.assert_called_once()


class LoadFallbackHashVerificationTest(unittest.TestCase):
    """_load_fallback() must refuse to pair a .mp3 with a .json sidecar whose recorded audioSha256
    doesn't match the .mp3's actual bytes -- an interrupted regeneration or partial commit could
    otherwise leave new audio paired with stale text (or vice versa), and invoke_speak() would
    authorize playback for the wrong sentence. Exercises _load_fallback() directly against temp
    files rather than mocking it, since the mocked tests elsewhere bypass this check entirely."""

    def setUp(self):
        polly_module._fallback_audio_b64 = None
        polly_module._fallback_text = None
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self.audio_path = tmp_path / "speak_fallback.mp3"
        self.metadata_path = tmp_path / "speak_fallback.json"
        self._patchers = [
            patch.object(polly_module, "FALLBACK_AUDIO_PATH", self.audio_path),
            patch.object(polly_module, "FALLBACK_METADATA_PATH", self.metadata_path),
        ]
        for patcher in self._patchers:
            patcher.start()

    def tearDown(self):
        for patcher in self._patchers:
            patcher.stop()
        self._tmpdir.cleanup()
        polly_module._fallback_audio_b64 = None
        polly_module._fallback_text = None

    def test_hash_mismatch_returns_none_none(self):
        self.audio_path.write_bytes(b"real-audio-bytes")
        self.metadata_path.write_text(
            json.dumps({"text": FALLBACK_TEXT, "voice": "Kevin", "engine": "neural", "audioSha256": "0" * 64})
        )

        result = _load_fallback()

        self.assertEqual(result, (None, None))

    def test_hash_match_returns_audio_and_text(self):
        audio_bytes = b"real-audio-bytes"
        self.audio_path.write_bytes(audio_bytes)
        self.metadata_path.write_text(
            json.dumps(
                {
                    "text": FALLBACK_TEXT,
                    "voice": "Kevin",
                    "engine": "neural",
                    "audioSha256": hashlib.sha256(audio_bytes).hexdigest(),
                }
            )
        )

        audio_b64, text = _load_fallback()

        self.assertEqual(base64.b64decode(audio_b64), audio_bytes)
        self.assertEqual(text, FALLBACK_TEXT)

    def test_missing_audio_sha256_field_returns_none_none(self):
        self.audio_path.write_bytes(b"real-audio-bytes")
        self.metadata_path.write_text(json.dumps({"text": FALLBACK_TEXT, "voice": "Kevin", "engine": "neural"}))

        result = _load_fallback()

        self.assertEqual(result, (None, None))

    def test_non_object_sidecar_returns_none_none(self):
        # Valid JSON, but not an object -- metadata["audioSha256"] would otherwise raise a TypeError
        # that isn't caught, crashing the Lambda instead of degrading to "no safe fallback."
        audio_bytes = b"real-audio-bytes"
        self.audio_path.write_bytes(audio_bytes)
        self.metadata_path.write_text(json.dumps([FALLBACK_TEXT, "Kevin", "neural"]))

        result = _load_fallback()

        self.assertEqual(result, (None, None))

    def test_non_string_text_returns_none_none(self):
        # A well-formed object, but "text" isn't a string -- must be rejected here rather than
        # leaking a non-string into _normalize()'s .strip() call later and crashing there instead.
        audio_bytes = b"real-audio-bytes"
        self.audio_path.write_bytes(audio_bytes)
        self.metadata_path.write_text(
            json.dumps(
                {
                    "text": 12345,
                    "voice": "Kevin",
                    "engine": "neural",
                    "audioSha256": hashlib.sha256(audio_bytes).hexdigest(),
                }
            )
        )

        result = _load_fallback()

        self.assertEqual(result, (None, None))

    def test_empty_audio_file_returns_none_none(self):
        self.audio_path.write_bytes(b"")
        self.metadata_path.write_text(
            json.dumps(
                {
                    "text": FALLBACK_TEXT,
                    "voice": "Kevin",
                    "engine": "neural",
                    "audioSha256": hashlib.sha256(b"").hexdigest(),
                }
            )
        )

        result = _load_fallback()

        self.assertEqual(result, (None, None))


@unittest.skipUnless(
    FALLBACK_AUDIO_PATH.exists() and FALLBACK_METADATA_PATH.exists(),
    "backend/fixtures/speak_fallback.{mp3,json} not generated yet -- "
    "run scripts/generate_speak_fallback.py with valid AWS credentials first",
)
class BundledFallbackClipTest(unittest.TestCase):
    """Sanity checks on the actual checked-in fallback asset once it exists. This can't verify the
    .mp3's spoken content (no ASR here) -- it only guards against the file being empty/corrupt and
    the metadata being malformed or missing the fields invoke_speak() relies on."""

    def test_metadata_has_required_fields(self):
        metadata = json.loads(FALLBACK_METADATA_PATH.read_text(encoding="utf-8"))
        self.assertIn("text", metadata)
        self.assertTrue(metadata["text"].strip())
        self.assertIn("voice", metadata)
        self.assertIn("engine", metadata)
        self.assertIn("audioSha256", metadata)

    def test_audio_file_is_non_empty(self):
        self.assertGreater(FALLBACK_AUDIO_PATH.stat().st_size, 0)

    def test_audio_sha256_matches_bundled_clip(self):
        # Regression guard for the checked-in pair specifically -- catches the .mp3 and .json
        # having drifted apart in a commit, not just _load_fallback()'s runtime behavior.
        metadata = json.loads(FALLBACK_METADATA_PATH.read_text(encoding="utf-8"))
        actual_sha256 = hashlib.sha256(FALLBACK_AUDIO_PATH.read_bytes()).hexdigest()
        self.assertEqual(actual_sha256, metadata["audioSha256"])

    @patch("src.common.polly.get_client")
    def test_end_to_end_fallback_matches_bundled_text(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.synthesize_speech.side_effect = _client_error("ThrottlingException")
        mock_get_client.return_value = mock_client

        metadata = json.loads(FALLBACK_METADATA_PATH.read_text(encoding="utf-8"))
        result = speak_handler({"body": json.dumps({"text": metadata["text"]})}, None)
        body = json.loads(result["body"])

        self.assertEqual(body["source"], "fallback")
        self.assertIsNotNone(body["audioBase64"])
        self.assertEqual(
            base64.b64decode(body["audioBase64"]), FALLBACK_AUDIO_PATH.read_bytes()
        )


if __name__ == "__main__":
    unittest.main()
