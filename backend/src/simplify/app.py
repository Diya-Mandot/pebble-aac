"""POST /simplify — mock handler. Matches submitted text against known fixtures; anything
unrecognized returns a labeled PLEASE_REPEAT fallback rather than a canned transcript, so the
"verbatim never silently edited" rule (PLAN.md) holds for every input, not just the scripted demo
line. Swap the fixture matching for a real Bedrock call later without changing the response
contract (see PLAN.md's API contract section).
"""
import json
from pathlib import Path

from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_simplify_request

FIXTURES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "simplify_fixtures.json"


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_simplify_request(payload)
    if error:
        return bad_request(error)

    text = payload["text"]
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    normalized = _normalize(text)
    match = next((f for f in fixtures if _normalize(f["input"]) == normalized), None)

    if match is None:
        return ok(
            {
                "steps": [],
                "warnings": [],
                "quickReplies": ["NEED_HELP"],
                "transcript": text,
                "status": "please_repeat",
            },
            source="fallback",
        )

    response = dict(match["response"])
    response["transcript"] = text
    return ok(response, source="mock")
