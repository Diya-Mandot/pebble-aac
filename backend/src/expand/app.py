"""POST /expand — live handler. Calls the pinned Bedrock model for schema-constrained,
profile-aware candidates (see expand/prompt.py); falls back to the matching fixture profile's
canned candidates when the request matches the scripted demo, or a generic deterministic
response otherwise, if the live call can't be trusted (see ../common/bedrock.py). Matches the
response contract from PLAN.md's API contract section."""
import json
from pathlib import Path

from ..common.bedrock import invoke_expand
from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_expand_request

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "expand_default.json"


def _load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _resolve_profile(fixture, profile_id):
    profiles = fixture["profiles"]
    return profiles.get(profile_id, profiles[fixture["defaultProfileId"]])


def _scripted_fallback_candidates(fixture, profile_id, icons, context):
    """Only return a scripted response when the request matches the fixture's scripted demo
    request verbatim -- an unscripted icon combination must fall through to the generic
    deterministic fallback in bedrock.py rather than showing a canned answer for the wrong
    request."""
    request = fixture.get("request")
    if request is None or request["icons"] != list(icons) or request["context"] != context:
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
    profile = _resolve_profile(fixture, payload["profileId"])["profile"]
    fallback_candidates = _scripted_fallback_candidates(
        fixture, payload["profileId"], payload["icons"], payload["context"]
    )

    get_remaining_ms = context.get_remaining_time_in_millis if context is not None else (lambda: None)
    candidates, source = invoke_expand(
        payload["icons"], payload["context"], profile, fallback_candidates, get_remaining_ms
    )
    return ok({"candidates": candidates}, source=source)
