"""Polly wiring for POST /speak — synthesizes the approved message with the pinned neural voice,
with a labeled fallback (the one bundled prerecorded clip) whenever the live call can't be trusted.

The bundled clip is a recording of ONE fixed sentence. Unlike /expand's deterministic fallback
(derived from the submitted icons) or /simplify's PLEASE_REPEAT (which invents no content), there is
no safe way to synthesize arbitrary approved text without Polly: playing the clip for text it
doesn't match would speak words the student never approved. So invoke_speak only ever returns the
clip when the requested text matches what it actually says (see _load_fallback/_normalize below);
for anything else, a failed live call returns no audio at all rather than the wrong one.

PLAN.md: "Every AWS call has a hard fallback (canned JSON, labeled on screen)." Also: "Fallbacks are
labeled. Any canned output shows 'Recorded demo fallback' on screen. Never disguised as live."
"""
import base64
import hashlib
import json
import sys
from contextlib import closing
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import (
    AWS_REGION,
    MAX_RETRIES,
    POLLY_CONNECT_TIMEOUT_SECONDS,
    POLLY_ENGINE,
    POLLY_OUTPUT_FORMAT,
    POLLY_READ_TIMEOUT_SECONDS,
    POLLY_VOICE_ID,
)

FALLBACK_AUDIO_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "speak_fallback.mp3"
FALLBACK_METADATA_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "speak_fallback.json"

PERMANENT_ERROR_CODES = {
    "AccessDeniedException",
    "ValidationException",
    "TextLengthExceededException",
    "InvalidSampleRateException",
    "InvalidSsmlException",
    "LexiconNotFoundException",
    "EngineNotSupportedException",
    "LanguageNotSupportedException",
}

# Below this much remaining Lambda time, don't start another attempt — go straight to fallback.
MIN_MS_FOR_ATTEMPT = (POLLY_CONNECT_TIMEOUT_SECONDS + POLLY_READ_TIMEOUT_SECONDS + 2) * 1000

_client = None
_fallback_audio_b64 = None
_fallback_text = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "polly",
            region_name=AWS_REGION,
            config=Config(
                connect_timeout=POLLY_CONNECT_TIMEOUT_SECONDS,
                read_timeout=POLLY_READ_TIMEOUT_SECONDS,
                # total_max_attempts (not max_attempts) caps this at exactly one attempt with zero
                # SDK-level retries -- see bedrock.py's get_client() for why (this application-level
                # MAX_RETRIES is the only retry budget in play).
                retries={"mode": "standard", "total_max_attempts": 1},
            ),
        )
    return _client


def _log_failure(exc, attempt, endpoint="speak"):
    # Only the failure type and attempt number -- never the spoken text (PLAN.md privacy rule:
    # "no transcripts/prompts/profiles in logs" -- this is the child's chosen words).
    sys.stderr.write(f"[{endpoint}] Polly attempt {attempt} failed: {type(exc).__name__}\n")


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _load_fallback():
    """Returns (audio_base64, text), or (None, None) if the bundled clip hasn't been generated yet
    (scripts/generate_speak_fallback.py), is otherwise unreadable/corrupt, has malformed metadata
    (not a JSON object, or missing/wrong-typed "text"/"audioSha256" fields), or the .mp3's bytes
    don't match the .json sidecar's recorded audioSha256 -- callers must treat all of that the same
    as "no safe fallback for this text" rather than letting it crash the request, same spirit as
    every other hard-fallback path in this codebase never raising past the caller.

    The hash check guards against the .mp3 and .json drifting apart (an interrupted regeneration, a
    partial commit, a stale file left over from a previous voice/text) and being paired anyway --
    that could authorize playback of the wrong clip for whatever text happens to be in the .json.
    The type checks guard against valid-but-wrong-shaped JSON (e.g. a top-level list, or a "text"
    that isn't a string) that would otherwise raise past this function -- TypeError from indexing a
    list, or later inside _normalize()'s .strip() if a non-string "text" leaked out."""
    global _fallback_audio_b64, _fallback_text
    if _fallback_audio_b64 is None:
        try:
            audio_bytes = FALLBACK_AUDIO_PATH.read_bytes()
            if not audio_bytes:
                raise ValueError("speak_fallback.mp3 is empty")

            metadata = json.loads(FALLBACK_METADATA_PATH.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError(f"speak_fallback.json must decode to an object, got {type(metadata).__name__}")

            text = metadata.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("speak_fallback.json's 'text' must be a non-empty string")

            expected_sha256 = metadata.get("audioSha256")
            if not isinstance(expected_sha256, str) or not expected_sha256:
                raise ValueError("speak_fallback.json's 'audioSha256' must be a non-empty string")

            actual_sha256 = hashlib.sha256(audio_bytes).hexdigest()
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    "speak_fallback.mp3 does not match speak_fallback.json's audioSha256 "
                    f"(expected {expected_sha256}, got {actual_sha256})"
                )
            _fallback_audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            _fallback_text = text
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _log_failure(exc, attempt=0)
            return None, None
    return _fallback_audio_b64, _fallback_text


def _call_once(text):
    response = get_client().synthesize_speech(
        Text=text,
        OutputFormat=POLLY_OUTPUT_FORMAT,
        VoiceId=POLLY_VOICE_ID,
        Engine=POLLY_ENGINE,
    )
    audio_stream = response.get("AudioStream")
    if audio_stream is None:
        raise ValueError("Polly response did not include an AudioStream")

    # closing(...) guarantees the StreamingBody is closed on every exit path -- success, a
    # wrong-content-type raise, or a .read() exception -- so a warm Lambda invocation reusing this
    # process never leaks the underlying HTTP connection.
    with closing(audio_stream):
        if response.get("ContentType") != "audio/mpeg":
            raise ValueError(f"Unexpected ContentType from Polly: {response.get('ContentType')}")
        audio_bytes = audio_stream.read()

    if not audio_bytes:
        raise ValueError("Empty audio stream from Polly")
    return audio_bytes


def invoke_speak(text, get_remaining_ms):
    """Returns (audio_base64_or_None, source). source is "live" on a validated Polly response,
    else "fallback". audio_base64 is None only when source is "fallback" and the requested text
    doesn't match the one bundled recorded clip -- see module docstring for why /speak must never
    substitute a different sentence's audio for what the student actually approved.
    get_remaining_ms is a zero-arg callable re-checked before each attempt (real Lambda context
    under API Gateway, or a lambda returning None under local_server.py's synthetic invocation,
    which is treated as "assume enough time")."""
    attempts = 1 + MAX_RETRIES
    for attempt in range(1, attempts + 1):
        remaining_ms = get_remaining_ms()
        if remaining_ms is not None and remaining_ms < MIN_MS_FOR_ATTEMPT:
            _log_failure(TimeoutError("insufficient remaining Lambda time"), attempt)
            break

        try:
            audio_bytes = _call_once(text)
        except ClientError as exc:
            _log_failure(exc, attempt)
            if exc.response.get("Error", {}).get("Code") in PERMANENT_ERROR_CODES:
                break
            continue
        except Exception as exc:  # network errors, timeouts, malformed stream, etc.
            _log_failure(exc, attempt)
            continue

        return base64.b64encode(audio_bytes).decode("ascii"), "live"

    fallback_audio_b64, fallback_text = _load_fallback()
    if fallback_text is not None and _normalize(text) == _normalize(fallback_text):
        return fallback_audio_b64, "fallback"
    return None, "fallback"
