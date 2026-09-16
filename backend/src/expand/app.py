"""POST /expand — mock handler. Loads fixture-shaped candidates; swap for a real Bedrock call later
without changing the response contract (see PLAN.md's API contract section)."""
import json
from pathlib import Path

from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_expand_request

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "expand_default.json"


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_expand_request(payload)
    if error:
        return bad_request(error)

    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return ok(fixture, source="mock")
