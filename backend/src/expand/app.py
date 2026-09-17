"""POST /expand — live handler. Calls the pinned Bedrock model for schema-constrained,
profile-aware candidates (see expand/prompt.py); falls back to the matching fixture profile's
canned candidates when the request matches the scripted demo, or a generic deterministic
response otherwise, if the live call can't be trusted (see ../common/bedrock.py). Matches the
response contract from PLAN.md's API contract section."""
import json
from pathlib import Path

from ..common.bedrock import invoke_expand
from ..common.dynamo import get_profile
from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_expand_request

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "expand_default.json"


def _load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _resolve_profile(fixture, profile_id):
    profiles = fixture["profiles"]
    return profiles.get(profile_id, profiles[fixture["defaultProfileId"]])


def _resolve_live_profile_traits(fixture, profile_id):
    """Returns (profile_traits, source). source distinguishes a real saved override ("live",
    POST /profile/{id}) from traits that are still exactly the fixture's ("fallback") -- the
    caller uses this to decide whether the fixture's canned scripted-demo candidates are still a
    safe stand-in if Bedrock fails: they're only safe when the profile actually in use IS the
    fixture's, not some saved override with different vocabLevel/tone/interests the canned strings
    were never written for."""
    saved, source = get_profile(profile_id)  # DynamoDB, itself already fixture-backed on miss/error
    if saved is not None:
        return saved, source
    return _resolve_profile(fixture, fixture["defaultProfileId"])["profile"], "fallback"


def _scripted_fallback_candidates(fixture, profile_id, tokens, context):
    """Only return a scripted response when the request matches the fixture's scripted demo
    request verbatim -- every token must be an icon (no word tokens), in the exact order
    `request["icons"]` was recorded for. An unscripted combination (including any word tokens)
    must fall through to the generic deterministic fallback in bedrock.py rather than showing a
    canned answer for the wrong request."""
    request = fixture.get("request")
    if request is None or any(token["kind"] != "icon" for token in tokens):
        return None
    icon_ids = [token["id"] for token in tokens]
    if icon_ids != request["icons"] or request["context"] != context:
        return None
    return _resolve_profile(fixture, profile_id)["response"]["candidates"]


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_expand_request(payload)
    if error:
        return bad_request(error)

    fixture = _load_fixture()
    profile, profile_source = _resolve_live_profile_traits(fixture, payload["profileId"])
    fallback_candidates = (
        _scripted_fallback_candidates(
            fixture, payload["profileId"], payload["tokens"], payload["context"]
        )
        if profile_source == "fallback"
        else None  # a saved DynamoDB override -- the fixture's canned strings weren't written
        # for this profile's actual traits, so fall through to invoke_expand's own
        # generic token-derived fallback instead of misrepresenting the override's voice.
    )

    get_remaining_ms = context.get_remaining_time_in_millis if context is not None else (lambda: None)
    candidates, source = invoke_expand(
        payload["tokens"], payload["context"], profile, fallback_candidates, get_remaining_ms
    )
    return ok({"candidates": candidates}, source=source)
