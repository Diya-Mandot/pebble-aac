"""POST /expand — live handler. Calls Bedrock with the Track A prompt/schema
(expand/prompt.py) to draft three candidate expansions of the submitted icons.

Profile lookup still reads the fixture file (no separate profile store exists yet);
unknown profileId falls back to the documented default, same as before. While
BEDROCK_MODEL_ID/AWS_REGION are still TODO placeholders (PLAN.md "Next 60 minutes"
item 5, blocked on AWS account access), this returns the fixture's canned candidates
labeled source:"mock" so local dev and tests don't need live AWS access. Once
configured: a valid Bedrock response is labeled source:"live"; a failed call or two
rounds of invalid tool output (1 retry) falls back to the same fixture candidates,
labeled source:"fallback" per PLAN.md's "fallbacks are labeled" rule.
"""
import json
from pathlib import Path

from ..common.bedrock import bedrock_configured, invoke_tool
from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_expand_request, validate_expand_output
from .prompt import EXPAND_SYSTEM_PROMPT, EXPAND_TOOL_CONFIG, build_expand_prompt

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "expand_default.json"


def _fixture_profile(profile_id: str) -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    profiles = fixture["profiles"]
    default_profile_id = fixture["defaultProfileId"]
    return profiles.get(profile_id, profiles[default_profile_id])


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_expand_request(payload)
    if error:
        return bad_request(error)

    selected = _fixture_profile(payload["profileId"])

    if not bedrock_configured():
        return ok(selected["response"], source="mock")

    prompt = build_expand_prompt(payload["icons"], payload["context"], selected["profile"])
    tool_input, error = invoke_tool(
        EXPAND_SYSTEM_PROMPT, prompt, EXPAND_TOOL_CONFIG, validate_expand_output
    )
    if error:
        return ok(selected["response"], source="fallback")

    return ok(tool_input, source="live")
