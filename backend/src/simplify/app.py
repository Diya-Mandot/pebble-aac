"""POST /simplify — live handler. Calls Bedrock with the Track B prompt/schema
(simplify/prompt.py, simplify/schema.py) to convert peer speech into a simplified
icon sequence.

While BEDROCK_MODEL_ID/AWS_REGION are still TODO placeholders (PLAN.md "Next 60
minutes" item 5, blocked on AWS account access), this matches submitted text against
the known fixtures and returns a labeled PLEASE_REPEAT fallback for anything
unrecognized, same as before, so local dev and tests don't need live AWS access. Once
configured: a valid Bedrock response is labeled source:"live"; a failed call or two
rounds of invalid tool output (1 retry) falls back to the same labeled PLEASE_REPEAT
response, source:"fallback" — the "verbatim never silently edited" rule holds either
way, since `transcript` is always the submitted text, never model or fixture output.
"""
import json
from pathlib import Path

from ..common.bedrock import bedrock_configured, invoke_tool
from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_simplify_request
from .prompt import SIMPLIFY_SYSTEM_PROMPT
from .schema import SIMPLIFY_TOOL_SCHEMA, validate_simplify_tool_output

FIXTURES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "simplify_fixtures.json"

# Bedrock's Converse API wants toolSpec/inputSchema.json; schema.py's SIMPLIFY_TOOL_SCHEMA
# is kept in the frozen Anthropic-tool shape (name/description/input_schema) since that's
# the shape Ben's Lambda-side validator and the fixtures were written against. Adapt here,
# at the wiring layer, rather than changing the frozen schema shape.
SIMPLIFY_TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": SIMPLIFY_TOOL_SCHEMA["name"],
                "description": SIMPLIFY_TOOL_SCHEMA["description"],
                "inputSchema": {"json": SIMPLIFY_TOOL_SCHEMA["input_schema"]},
            }
        }
    ],
    "toolChoice": {"tool": {"name": SIMPLIFY_TOOL_SCHEMA["name"]}},
}


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _please_repeat(text: str) -> dict:
    return {
        "steps": [],
        "warnings": [],
        "quickReplies": ["NEED_HELP"],
        "transcript": text,
        "status": "please_repeat",
    }


def _fixture_match(text: str):
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    normalized = _normalize(text)
    return next((f for f in fixtures if _normalize(f["input"]) == normalized), None)


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_simplify_request(payload)
    if error:
        return bad_request(error)

    text = payload["text"]

    if not bedrock_configured():
        match = _fixture_match(text)
        if match is None:
            return ok(_please_repeat(text), source="fallback")
        response = dict(match["response"])
        response["transcript"] = text
        return ok(response, source="mock")

    tool_input, error = invoke_tool(
        SIMPLIFY_SYSTEM_PROMPT, text, SIMPLIFY_TOOL_CONFIG, validate_simplify_tool_output
    )
    if error:
        return ok(_please_repeat(text), source="fallback")

    response = dict(tool_input)
    response["transcript"] = text
    return ok(response, source="live")
